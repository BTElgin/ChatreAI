import functools
import json
import logging
from typing import Optional, TypedDict

import anthropic
from langgraph.graph import END, StateGraph

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
        "description": "what Cadre AI does, and whether it serves the asker's industry",
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
        "existing_customer": {"type": "boolean"},
    },
    "required": ["intents", "has_unaddressed_scope", "existing_customer"],
    "additionalProperties": False,
}

CLASSIFY_SYSTEM = f"""Identify which of the following categories the user's LATEST message touches. A message can touch zero, one, or several. You may be shown earlier turns of the conversation first — use them only as context for interpreting the latest message (e.g. a short follow-up like "what about healthcare?" should be read against what was just discussed), not as something to classify themselves.

{INTENT_DESCRIPTIONS}

Also set has_unaddressed_scope to true if any part of the latest message is not covered by the categories above — this includes messages that are genuinely ambiguous or unclear, and multi-part messages where only some parts match a category.

Also set existing_customer to true if anywhere in the conversation the user has indicated they are already a paying Cadre AI client — e.g. they mention their account, an AI agent or system Cadre already built for them, their account manager, or say directly that they're already a client. Default to false; do not infer this just because someone asks a detailed or technical question."""

ANSWER_VOICE_BASE = (
    "You are the support assistant for Cadre AI, a B2B AI strategy and implementation "
    "consultancy. Voice: professional but approachable, not overly casual and not stiff, "
    "and always encouraging and supportive — sound like you're rooting for the person's "
    "business, even when redirecting or admitting something is out of scope. "
    "Answer only using the knowledge below. Do not invent services, pricing, policies, or "
    "URLs that are not present in it. If the knowledge only covers part of what was asked, "
    "answer that part and leave the rest alone rather than guessing. When the knowledge "
    "includes a booking URL, present it as a markdown link (e.g. [book a call](<url>)) "
    "rather than pasting the raw URL or only describing it."
)

ANSWER_VOICE_PROSPECT_ADDENDUM = (
    " Where it's natural, point out a specific, concrete way Cadre could help improve "
    "this person's business given what they've shared — not a generic sales pitch, just "
    "an honest, supportive nudge toward how Cadre applies to their situation."
)

ANSWER_VOICE_CUSTOMER_ADDENDUM = (
    " This person is an existing Cadre AI client — speak to them like a client, not a "
    "prospect. Focus on getting more value out of what they already have and point out "
    "other Cadre services that could complement their current engagement. Don't pitch "
    "them on becoming a client; they already are one."
)

ESCALATION_CTA = f"[book a call with a Cadre AI strategist]({BOOKING_URL}), who can dig into specifics with you"
EXISTING_CUSTOMER_ESCALATION_CTA = "reach out to your Cadre engagement lead directly, who can dig into specifics with you"


def _escalation_cta(existing_customer: bool) -> str:
    return EXISTING_CUSTOMER_ESCALATION_CTA if existing_customer else ESCALATION_CTA


def _escalation_message(existing_customer: bool) -> str:
    return f"That's outside what I can help with directly. The best next step is to {_escalation_cta(existing_customer)}."


def _partial_escalation_note(existing_customer: bool) -> str:
    return (
        f"\n\nOne part of your question is outside what I can help with directly here — "
        f"for that, the best next step is to {_escalation_cta(existing_customer)}."
    )


# Prospect-facing defaults — used as the safe fallback where no existing_customer
# signal exists yet (e.g. main.py's outer exception handler, which catches errors
# before/outside the graph and so has no state to read the flag from).
ESCALATION_MESSAGE = _escalation_message(False)
PARTIAL_ESCALATION_NOTE = _partial_escalation_note(False)

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
    existing_customer: bool
    knowledge_used: list[str]
    draft_answer: Optional[str]
    escalate: bool
    response: str
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
            max_tokens=150,
            output_config={"format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA}},
            system=CLASSIFY_SYSTEM,
            messages=_conversation(state),
        )
        data = json.loads(_first_text(response))
        intents = [i for i in data["intents"] if i in KNOWN_INTENTS]
        has_unaddressed_scope = bool(data["has_unaddressed_scope"])
        existing_customer = bool(data["existing_customer"])
    except Exception:
        logger.exception("classify failed, defaulting to escalate")
        intents = []
        has_unaddressed_scope = True
        existing_customer = False
    logger.info(
        "classify: intents=%s has_unaddressed_scope=%s existing_customer=%s",
        intents,
        has_unaddressed_scope,
        existing_customer,
    )
    return {
        "intents": intents,
        "has_unaddressed_scope": has_unaddressed_scope,
        "existing_customer": existing_customer,
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
    draft = None
    try:
        response = _client().messages.create(
            model=ANSWER_MODEL,
            max_tokens=1024,
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


def escalation_check(state: ChatState) -> ChatState:
    escalate = not state["intents"] or not state.get("draft_answer")
    logger.info(
        "escalation_check: intents=%s has_unaddressed_scope=%s escalate=%s",
        state["intents"],
        state["has_unaddressed_scope"],
        escalate,
    )
    return {"escalate": escalate}


def respond(state: ChatState) -> ChatState:
    existing_customer = state.get("existing_customer", False)
    if state["escalate"]:
        return {"response": _escalation_message(existing_customer)}
    response = state["draft_answer"]
    if state["has_unaddressed_scope"]:
        response = f"{response}{_partial_escalation_note(existing_customer)}"
    return {"response": response}


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
    graph.add_node("suggest_followups", suggest_followups)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "answer")
    graph.add_edge("answer", "escalation_check")
    graph.add_edge("escalation_check", "respond")
    graph.add_edge("respond", "suggest_followups")
    graph.add_edge("suggest_followups", END)

    return graph.compile()


_compiled_graph = build_graph()


def run_chat(message: str, history: Optional[list[dict]] = None) -> ChatState:
    windowed_history = (history or [])[-HISTORY_WINDOW:]
    return _compiled_graph.invoke({"message": message, "history": windowed_history})
