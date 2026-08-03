import functools
import json
import logging
from typing import Optional, TypedDict

import anthropic
from langgraph.graph import END, StateGraph

from app import lead
from app.config import BOOKING_URL
from app.prompt import load_knowledge

logger = logging.getLogger("cadre_chat")

# Model routing: cheap/fast Haiku for classification and suggestion generation
# (simple, structured, low-stakes tasks), Opus reserved for the actual
# knowledge-grounded answer (the one place quality genuinely matters).
CLASSIFY_MODEL = "claude-haiku-4-5"
SUGGEST_MODEL = "claude-haiku-4-5"
ANSWER_MODEL = "claude-opus-5"

HISTORY_WINDOW = 20  # last N messages (~10 exchanges) kept as context; older turns drop off
MAX_SUGGESTIONS = 3

# Single source of truth for the 7 classifiable intents: what they mean (for
# the classify/suggest prompts) and which knowledge/cadre.json keys answer
# them. KNOWN_INTENTS, INTENT_KNOWLEDGE_KEYS, and INTENT_DESCRIPTIONS all
# derive from this so a new intent only needs one entry, not three.
INTENTS = {
    "about_and_industries": {
        "description": (
            "what Cadre AI does and its services, whether it serves the asker's industry, or — "
            "for an existing client — what else Cadre offers that could help them get more value "
            "or expand their current engagement"
        ),
        "knowledge_keys": ["company", "services", "industries_served"],
    },
    "booking": {
        "description": "how to book a call with an AI strategist, or how to get started",
        "knowledge_keys": ["booking"],
    },
    "client_portal": {
        "description": "how to access the Cadre client portal",
        "knowledge_keys": ["client_portal"],
    },
    "ai_maturity_index": {
        "description": "what the AI Maturity Index is and how to get scored",
        "knowledge_keys": ["ai_maturity_index"],
    },
    "llm_and_data_security": {
        "description": "Cadre's approach to LLM selection and data security",
        "knowledge_keys": ["llm_and_data_security"],
    },
    "pricing": {
        "description": "how much Cadre's services cost, or how pricing works",
        "knowledge_keys": ["pricing"],
    },
    "case_studies": {
        "description": "examples of results Cadre has delivered for clients, case studies, success stories",
        "knowledge_keys": ["case_studies"],
    },
}

KNOWN_INTENTS = list(INTENTS)
INTENT_KNOWLEDGE_KEYS = {intent: info["knowledge_keys"] for intent, info in INTENTS.items()}
INTENT_DESCRIPTIONS = "\n".join(f"- {intent}: {info['description']}" for intent, info in INTENTS.items())

# Starter prompts shown in the UI before a conversation begins. Kept here so
# backend and frontend stay in sync on what the "common inquiries" are.
STARTER_PROMPTS = [
    "What does Cadre AI do?",
    "How do I get started?",
    "What do your services cost?",
    "What's the AI Maturity Index?",
    "Do you have case studies?",
    "How do I book a strategy call?",
    "What industries do you work with?",
]

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "intents": {
            "type": "array",
            "items": {"type": "string", "enum": KNOWN_INTENTS},
        },
        "has_unaddressed_scope": {"type": "boolean"},
        "unaddressed_scope_summary": {"type": "string"},
        "existing_customer": {"type": "boolean"},
        "is_greeting": {"type": "boolean"},
        **lead.PROFILE_SCHEMA_PROPERTIES,
    },
    "required": [
        "intents",
        "has_unaddressed_scope",
        "unaddressed_scope_summary",
        "existing_customer",
        "is_greeting",
        *lead.PROFILE_FIELDS,
    ],
    "additionalProperties": False,
}

CLASSIFY_SYSTEM = f"""Identify which of the following categories the user's LATEST message touches. A message can touch zero, one, or several. You may be shown earlier turns of the conversation first — use them only as context for interpreting the latest message (e.g. a short follow-up like "what about healthcare?" should be read against what was just discussed), not as something to classify themselves.

{INTENT_DESCRIPTIONS}

Also set has_unaddressed_scope to true if any part of the latest message is not covered by the categories above — this includes messages that are genuinely ambiguous or unclear, and multi-part messages where only some parts match a category. When you set it to true, also set unaddressed_scope_summary to a short phrase (a few words, not a full sentence) naming that specific part — written so it reads naturally inserted into "One part of your question — {{summary}} — is outside what I can help with directly here." For example: "the cookie recipe question", "custom contract terms", "integrating with your existing CRM". Use an empty string when has_unaddressed_scope is false.

Also set existing_customer to true if anywhere in the conversation the user has indicated they are already a paying Cadre AI client — e.g. they mention their account, an AI agent or system Cadre already built for them, their account manager, or say directly that they're already a client. Default to false; do not infer this just because someone asks a detailed or technical question.

Also set is_greeting to true if the latest message is ONLY a greeting or basic pleasantry (e.g. "hi", "hello", "hey", "good morning") with no actual question or request attached — even if it's the very first message in the conversation. If the message greets AND asks something, set this to false; the something is what matters.

Also extract any of the following the user has volunteered about themselves or their business, anywhere in the conversation so far: their name, business name, business type or category, phone number, and email address. Use an empty string for anything not mentioned. Only extract information the user actually stated — never invent, guess, or infer a value that wasn't given. This applies no matter what the conversation is about — extract it passively whenever it's there, don't wait for a specific topic."""

ANSWER_VOICE_BASE = (
    "You are the support assistant for Cadre AI, a B2B AI strategy and implementation "
    "consultancy. Voice: professional but approachable, not overly casual and not stiff, "
    "and always encouraging and supportive: sound like you're rooting for the person's "
    "business, even when redirecting or admitting something is out of scope. Write like a "
    "real person on the team dashing off a quick, thoughtful reply, not like polished "
    "marketing copy or a template. Skip stock openers like \"Happy to help\" or \"Great "
    "question\"; just answer. Use periods and commas the way people actually type instead "
    "of leaning on em dashes for every aside, and let sentences vary in length instead of "
    "sounding uniformly composed. "
    "This is a working session, not a document handoff: keep replies short (2-4 sentences, "
    "or a couple of short bullets at most) and converge on the ONE thing most relevant to "
    "what they just said, rather than covering every service, tier, or branch up front. If "
    "narrowing down would help, ask a single short clarifying question and stop there, and "
    "let the conversation unfold turn by turn instead of front-loading everything you could "
    "say. "
    "Answer only using the knowledge below. Do not invent services, pricing, policies, or "
    "URLs that are not present in it. If the knowledge only covers part of what was asked, "
    "answer that part and leave the rest alone rather than guessing. When the knowledge "
    "includes a booking URL, present it as a markdown link (e.g. [book a call](<url>)) "
    "rather than pasting the raw URL or only describing it."
)

ANSWER_VOICE_PROSPECT_ADDENDUM = (
    " Where it's natural, point out ONE specific, concrete way Cadre could help improve "
    "this person's business given what they've shared — not a generic sales pitch, and "
    "not a tour of every service, just an honest, supportive nudge toward the single "
    "thing most likely to matter to their situation."
)

ANSWER_VOICE_CUSTOMER_ADDENDUM = (
    " This person is an existing Cadre AI client — speak to them like a client, not a "
    "prospect. If it's natural, mention ONE Cadre service that could complement what "
    "they already have — never a rundown of all four — and ask what they're currently "
    "using before recommending more if that's unclear. Don't pitch them on becoming a "
    "client; they already are one."
)

# Appended when the lead_capture node has already asked for contact info and is
# waiting to hear back — without this, answer() (which has no idea lead_capture
# exists) will naturally write things like "someone will follow up" on its own,
# which then contradicts lead_capture's own delivery confirmation (or honest
# failure note) appended right after it in the same response.
ANSWER_VOICE_LEAD_PENDING_ADDENDUM = (
    " If this message includes the user's contact info, thank them briefly and keep "
    "answering their question — don't promise that someone will follow up or confirm "
    "their info was received; that confirmation is handled separately, right after this."
)

ESCALATION_CTA = f"[book a call with a Cadre AI strategist]({BOOKING_URL}), who can dig into specifics with you"
EXISTING_CUSTOMER_ESCALATION_CTA = "reach out to your Cadre engagement lead directly, who can dig into specifics with you"


def _escalation_cta(existing_customer: bool) -> str:
    return EXISTING_CUSTOMER_ESCALATION_CTA if existing_customer else ESCALATION_CTA


def _escalation_message(existing_customer: bool) -> str:
    return f"That's outside what I can help with directly. The best next step is to {_escalation_cta(existing_customer)}."


def _partial_escalation_note(existing_customer: bool, summary: str = "") -> str:
    detail = f" ({summary})" if summary else ""
    return (
        f"\n\nOne part of your question{detail} is outside what I can help with directly here. "
        f"For that, the best next step is to {_escalation_cta(existing_customer)}."
    )


# Prospect-facing defaults — used as the safe fallback where no existing_customer
# signal exists yet (e.g. main.py's outer exception handler, which catches errors
# before/outside the graph and so has no state to read the flag from).
ESCALATION_MESSAGE = _escalation_message(False)
PARTIAL_ESCALATION_NOTE = _partial_escalation_note(False)

# Shown instead of lead.LEAD_DELIVERED_NOTE when lead.deliver_lead() returns False
# (no webhook configured, or the POST failed) — never claim the info was sent
# anywhere when it wasn't; fall back to the same booking link every other escalation uses.
LEAD_DELIVERY_FALLBACK_NOTE = (
    f"Thanks for sharing that. I wasn't able to pass it along automatically just now, "
    f"so the fastest path from here is to {ESCALATION_CTA}."
)

# Shown for a standalone greeting (no other content in the message) instead of the
# full escalation message — a bare "hi" genuinely doesn't match any known intent,
# but treating it like an out-of-scope question and pushing a booking link on it
# is needlessly heavy-handed for a simple hello.
GREETING_RESPONSE = (
    "Hi there! I can help with questions about what Cadre does, pricing, case studies, "
    "booking a call, that kind of thing. What can I help you with?"
)
EXISTING_CUSTOMER_GREETING_RESPONSE = (
    "Hi there! Ask me anything about your engagement, or let me know if you'd like to "
    "explore other ways Cadre could help."
)

SUGGESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["suggestions"],
    "additionalProperties": False,
}

SUGGEST_SYSTEM = f"""Based on the conversation so far, suggest up to {MAX_SUGGESTIONS} short follow-up questions the user might naturally ask next about Cadre AI. Phrase each as a question in the user's own voice, under 8 words where possible.

Only suggest questions that fit within these topics:
{INTENT_DESCRIPTIONS}

If the conversation just escalated (nothing in scope matched the last question), suggest questions that pivot back to something answerable instead of repeating the same escalated topic. Return fewer than {MAX_SUGGESTIONS} suggestions, or an empty list, if nothing natural fits — don't force it."""


class ChatState(TypedDict, total=False):
    message: str
    history: list[dict]
    intents: list[str]
    has_unaddressed_scope: bool
    unaddressed_scope_summary: str
    existing_customer: bool
    is_greeting: bool
    knowledge_used: list[str]
    draft_answer: Optional[str]
    escalate: bool
    response: str
    profile: dict
    suggestions: list[str]


@functools.lru_cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def _conversation(state: ChatState, final_message: Optional[str] = None) -> list[dict]:
    content = final_message if final_message is not None else state["message"]
    return [*state.get("history", []), {"role": "user", "content": content}]


def _first_text(response) -> str:
    return next(block.text for block in response.content if block.type == "text")


def classify(state: ChatState) -> ChatState:
    try:
        response = _client().messages.create(
            model=CLASSIFY_MODEL,
            max_tokens=350,
            output_config={"format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA}},
            system=CLASSIFY_SYSTEM,
            messages=_conversation(state),
        )
        data = json.loads(_first_text(response))
        intents = [i for i in data["intents"] if i in KNOWN_INTENTS]
        has_unaddressed_scope = bool(data["has_unaddressed_scope"])
        unaddressed_scope_summary = data["unaddressed_scope_summary"] if has_unaddressed_scope else ""
        existing_customer = bool(data["existing_customer"])
        is_greeting = bool(data["is_greeting"])
        profile = lead.filter_profile(data)
    except Exception:
        logger.exception("classify failed, defaulting to escalate")
        intents = []
        has_unaddressed_scope = True
        unaddressed_scope_summary = ""
        existing_customer = False
        is_greeting = False
        profile = {}
    logger.info(
        "classify: intents=%s has_unaddressed_scope=%s unaddressed_scope_summary=%r existing_customer=%s is_greeting=%s profile_keys=%s",
        intents,
        has_unaddressed_scope,
        unaddressed_scope_summary,
        existing_customer,
        is_greeting,
        list(profile),
    )
    return {
        "intents": intents,
        "has_unaddressed_scope": has_unaddressed_scope,
        "unaddressed_scope_summary": unaddressed_scope_summary,
        "existing_customer": existing_customer,
        "is_greeting": is_greeting,
        "profile": profile,
    }


def answer(state: ChatState) -> ChatState:
    intents = state["intents"]
    if not intents:
        return {"draft_answer": None, "knowledge_used": []}

    keys = list(dict.fromkeys(k for intent in intents for k in INTENT_KNOWLEDGE_KEYS[intent]))

    knowledge = load_knowledge()
    scoped_knowledge = {k: knowledge[k] for k in keys if k in knowledge}
    voice = ANSWER_VOICE_BASE + (
        ANSWER_VOICE_CUSTOMER_ADDENDUM if state.get("existing_customer") else ANSWER_VOICE_PROSPECT_ADDENDUM
    )
    profile_name = state.get("profile", {}).get("name")
    if profile_name:
        voice += (
            f" The person's name is {profile_name} — use it naturally if it fits (e.g. a "
            "greeting or sign-off), don't force it into every sentence."
        )
    history = state.get("history", [])
    if lead.already_asked(history) and not lead.already_delivered(history):
        voice += ANSWER_VOICE_LEAD_PENDING_ADDENDUM
    draft = None
    try:
        response = _client().messages.create(
            model=ANSWER_MODEL,
            max_tokens=500,
            output_config={"effort": "low"},
            system=f"{voice}\n\n## Knowledge\n\n{json.dumps(scoped_knowledge, indent=2)}",
            messages=_conversation(state),
        )
        draft = _first_text(response)
    except Exception:
        logger.exception("answer failed for intents=%s", intents)
    logger.info(
        "answer: intents=%s knowledge_used=%s existing_customer=%s ok=%s",
        intents,
        keys,
        state.get("existing_customer", False),
        draft is not None,
    )
    return {"draft_answer": draft, "knowledge_used": keys}


def _is_greeting_only(state: ChatState) -> bool:
    return bool(state.get("is_greeting")) and not state["intents"]


def escalation_check(state: ChatState) -> ChatState:
    escalate = not _is_greeting_only(state) and (not state["intents"] or not state.get("draft_answer"))
    logger.info(
        "escalation_check: intents=%s has_unaddressed_scope=%s is_greeting_only=%s escalate=%s",
        state["intents"],
        state["has_unaddressed_scope"],
        _is_greeting_only(state),
        escalate,
    )
    return {"escalate": escalate}


def respond(state: ChatState) -> ChatState:
    existing_customer = state.get("existing_customer", False)
    if _is_greeting_only(state):
        return {"response": EXISTING_CUSTOMER_GREETING_RESPONSE if existing_customer else GREETING_RESPONSE}
    if state["escalate"]:
        return {"response": _escalation_message(existing_customer)}
    response = state["draft_answer"]
    if state["has_unaddressed_scope"]:
        summary = state.get("unaddressed_scope_summary", "")
        response = f"{response}{_partial_escalation_note(existing_customer, summary)}"
    return {"response": response}


def _capture_prospect_lead(state: ChatState, history: list[dict], response: str, profile: dict) -> ChatState:
    if lead.already_delivered(history):
        return {}

    if not lead.already_asked(history):
        # Two independent reasons to offer a human follow-up instead of just the
        # self-serve booking link: real buying intent (booking/pricing, and only
        # once there's been a prior exchange, so this doesn't pounce on message
        # one), or the bot just couldn't help directly at all -- escalating is
        # exactly the moment someone might not want to book a call themselves,
        # so this offer is relevant immediately, even on a first message.
        shows_intent = bool(history) and lead.shows_buying_intent(state.get("intents", []))
        is_escalating = state["escalate"] or state["has_unaddressed_scope"]
        if shows_intent or is_escalating:
            logger.info("lead_capture: asking for contact info")
            return {"response": f"{response}\n\n{lead.LEAD_ASK_PROMPT}"}
        return {}

    if not lead.is_lead_complete(profile):
        logger.info("lead_capture: profile still incomplete: %s", profile)
        return {}

    delivered = lead.deliver_lead(profile, {"intents": state.get("intents", []), "latest_message": state["message"]})
    note = lead.LEAD_DELIVERED_NOTE if delivered else LEAD_DELIVERY_FALLBACK_NOTE
    logger.info("lead_capture: profile complete, delivered=%s", delivered)
    if state["escalate"]:
        # The generic "that's outside what I can help with directly" framing
        # doesn't make sense as a lead-in when the user's own message was just
        # providing the contact info we asked for -- the delivery confirmation
        # (or honest fallback) IS the answer this turn, not a tacked-on addendum.
        return {"response": note}
    return {"response": f"{response}\n\n{note}"}


def _capture_customer_signal(state: ChatState, history: list[dict], response: str, profile: dict) -> ChatState:
    # No explicit ask for existing customers — this is purely passive (whatever
    # was volunteered elsewhere in the conversation) and lower-stakes than a new
    # lead: it's a context note for their own account team, not a sales handoff.
    # If delivery isn't configured, stay silent rather than narrating an internal
    # failure for something the user never asked to be sent anywhere.
    if not lead.is_customer_signal_worth_sending(profile):
        return {}
    if lead.already_delivered(history, marker=lead.CUSTOMER_SIGNAL_NOTE):
        return {}

    delivered = lead.deliver_lead(
        profile,
        {
            "signal_type": "existing_customer_engagement",
            "intents": state.get("intents", []),
            "latest_message": state["message"],
        },
    )
    if not delivered:
        return {}

    logger.info("lead_capture: existing-customer signal delivered: %s", profile)
    return {"response": f"{response}\n\n{lead.CUSTOMER_SIGNAL_NOTE}"}


def lead_capture(state: ChatState) -> ChatState:
    # Stateless by design, same as the rest of this graph: there's no session store,
    # so "have we already asked" / "has this already been delivered" is derived by
    # checking past assistant turns (replayed back as history by the frontend) for
    # the fixed marker strings in app/lead.py, not tracked server-side.
    if _is_greeting_only(state):
        return {}

    history = state.get("history", [])
    response = state["response"]
    profile = state.get("profile", {})

    if state.get("existing_customer"):
        # Existing customers already have a known point of contact (their
        # engagement lead) -- unlike prospects, an escalation doesn't need a
        # separate "have someone reach out" offer layered on top.
        if state["escalate"] or state["has_unaddressed_scope"]:
            return {}
        return _capture_customer_signal(state, history, response, profile)
    return _capture_prospect_lead(state, history, response, profile)


def suggest_followups(state: ChatState) -> ChatState:
    # Structured outputs reject a request ending in an `assistant` message (it
    # looks like a disallowed prefill), so the just-given answer is folded into
    # a final `user`-role message instead of appended as its own assistant turn.
    exchange_summary = (
        f'The user just asked: "{state["message"]}"\n'
        f'The assistant just answered: "{state["response"]}"\n\n'
        "Suggest natural follow-up questions."
    )
    suggestions = []
    try:
        response = _client().messages.create(
            model=SUGGEST_MODEL,
            max_tokens=150,
            output_config={"format": {"type": "json_schema", "schema": SUGGESTIONS_SCHEMA}},
            system=SUGGEST_SYSTEM,
            messages=_conversation(state, final_message=exchange_summary),
        )
        suggestions = list(json.loads(_first_text(response))["suggestions"])[:MAX_SUGGESTIONS]
    except Exception:
        logger.exception("suggest_followups failed, returning no suggestions")
    logger.info("suggest_followups: count=%d", len(suggestions))
    return {"suggestions": suggestions}


def build_graph():
    graph = StateGraph(ChatState)
    graph.add_node("classify", classify)
    graph.add_node("answer", answer)
    graph.add_node("escalation_check", escalation_check)
    graph.add_node("respond", respond)
    graph.add_node("lead_capture", lead_capture)
    graph.add_node("suggest_followups", suggest_followups)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "answer")
    graph.add_edge("answer", "escalation_check")
    graph.add_edge("escalation_check", "respond")
    graph.add_edge("respond", "lead_capture")
    graph.add_edge("lead_capture", "suggest_followups")
    graph.add_edge("suggest_followups", END)

    return graph.compile()


_compiled_graph = build_graph()


def run_chat(message: str, history: Optional[list[dict]] = None) -> ChatState:
    windowed_history = (history or [])[-HISTORY_WINDOW:]
    return _compiled_graph.invoke({"message": message, "history": windowed_history})
