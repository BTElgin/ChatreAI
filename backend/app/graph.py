import functools
import json
import logging
from typing import Optional, TypedDict

import anthropic
from langgraph.graph import END, StateGraph

from app.prompt import load_knowledge

logger = logging.getLogger("cadre_chat")

MODEL = "claude-opus-5"

KNOWN_INTENTS = [
    "about_and_industries",
    "booking",
    "client_portal",
    "ai_maturity_index",
    "llm_and_data_security",
]

INTENT_KNOWLEDGE_KEYS = {
    "about_and_industries": ["company", "services", "industries_served"],
    "booking": ["booking"],
    "client_portal": ["client_portal"],
    "ai_maturity_index": ["ai_maturity_index"],
    "llm_and_data_security": ["llm_and_data_security"],
}

INTENT_DESCRIPTIONS = """- about_and_industries: what Cadre AI does, and whether it serves the asker's industry
- booking: how to book a call with an AI strategist
- client_portal: how to access the Cadre client portal
- ai_maturity_index: what the AI Maturity Index is and how to get scored
- llm_and_data_security: Cadre's approach to LLM selection and data security"""

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "intents": {
            "type": "array",
            "items": {"type": "string", "enum": KNOWN_INTENTS},
        },
        "has_unaddressed_scope": {"type": "boolean"},
    },
    "required": ["intents", "has_unaddressed_scope"],
    "additionalProperties": False,
}

CLASSIFY_SYSTEM = f"""Identify which of the following categories the user's message touches. A message can touch zero, one, or several.

{INTENT_DESCRIPTIONS}

Also set has_unaddressed_scope to true if any part of the message is not covered by the categories above — this includes messages that are genuinely ambiguous or unclear, and multi-part messages where only some parts match a category."""

ANSWER_VOICE = (
    "You are the support assistant for Cadre AI, a B2B AI strategy and implementation "
    "consultancy. Voice: professional but approachable, not overly casual and not stiff. "
    "Answer only using the knowledge below. Do not invent services, pricing, policies, or "
    "URLs that are not present in it. If the knowledge only covers part of what was asked, "
    "answer that part and leave the rest alone rather than guessing."
)

ESCALATION_CTA = "book a call with a Cadre AI strategist, who can dig into specifics with you"
ESCALATION_MESSAGE = f"That's outside what I can help with directly. The best next step is to {ESCALATION_CTA}."
PARTIAL_ESCALATION_NOTE = (
    f"\n\nOne part of your question is outside what I can help with directly here — "
    f"for that, the best next step is to {ESCALATION_CTA}."
)


class ChatState(TypedDict, total=False):
    message: str
    intents: list[str]
    has_unaddressed_scope: bool
    knowledge_used: list[str]
    draft_answer: Optional[str]
    escalate: bool
    response: str


@functools.lru_cache
def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def classify(state: ChatState) -> ChatState:
    try:
        response = _client().messages.create(
            model=MODEL,
            max_tokens=150,
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA},
            },
            system=CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": state["message"]}],
        )
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        intents = [i for i in data["intents"] if i in KNOWN_INTENTS]
        has_unaddressed_scope = bool(data["has_unaddressed_scope"])
    except Exception:
        logger.exception("classify failed, defaulting to escalate")
        intents = []
        has_unaddressed_scope = True
    logger.info("classify: intents=%s has_unaddressed_scope=%s", intents, has_unaddressed_scope)
    return {"intents": intents, "has_unaddressed_scope": has_unaddressed_scope}


def answer(state: ChatState) -> ChatState:
    intents = state["intents"]
    if not intents:
        return {"draft_answer": None, "knowledge_used": []}

    keys = []
    for intent in intents:
        keys.extend(k for k in INTENT_KNOWLEDGE_KEYS[intent] if k not in keys)

    knowledge = load_knowledge()
    scoped_knowledge = {k: knowledge[k] for k in keys if k in knowledge}
    draft = None
    try:
        response = _client().messages.create(
            model=MODEL,
            max_tokens=1024,
            output_config={"effort": "low"},
            system=f"{ANSWER_VOICE}\n\n## Knowledge\n\n{json.dumps(scoped_knowledge, indent=2)}",
            messages=[{"role": "user", "content": state["message"]}],
        )
        draft = next(b.text for b in response.content if b.type == "text")
    except Exception:
        logger.exception("answer failed for intents=%s", intents)
    logger.info("answer: intents=%s knowledge_used=%s ok=%s", intents, keys, draft is not None)
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
    if state["escalate"]:
        return {"response": ESCALATION_MESSAGE}
    response = state["draft_answer"]
    if state["has_unaddressed_scope"]:
        response = f"{response}{PARTIAL_ESCALATION_NOTE}"
    return {"response": response}


def build_graph():
    graph = StateGraph(ChatState)
    graph.add_node("classify", classify)
    graph.add_node("answer", answer)
    graph.add_node("escalation_check", escalation_check)
    graph.add_node("respond", respond)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "answer")
    graph.add_edge("answer", "escalation_check")
    graph.add_edge("escalation_check", "respond")
    graph.add_edge("respond", END)

    return graph.compile()


_compiled_graph = build_graph()


def run_chat(message: str) -> ChatState:
    return _compiled_graph.invoke({"message": message})
