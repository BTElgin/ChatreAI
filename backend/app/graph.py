import functools
import json
import logging
from typing import Optional, TypedDict

import anthropic
from langgraph.graph import END, StateGraph

from app.prompt import load_knowledge

logger = logging.getLogger("cadre_chat")

MODEL = "claude-opus-5"

INTENTS = [
    "about_and_industries",
    "booking",
    "client_portal",
    "ai_maturity_index",
    "llm_and_data_security",
    "out_of_scope",
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
- llm_and_data_security: Cadre's approach to LLM selection and data security
- out_of_scope: anything else, including questions with no basis for an answer in the categories above"""

CLASSIFY_SCHEMA = {
    "type": "object",
    "properties": {"intent": {"type": "string", "enum": INTENTS}},
    "required": ["intent"],
    "additionalProperties": False,
}

ANSWER_VOICE = (
    "You are the support assistant for Cadre AI, a B2B AI strategy and implementation "
    "consultancy. Voice: professional but approachable, not overly casual and not stiff. "
    "Answer only using the knowledge below. Do not invent services, pricing, policies, or "
    "URLs that are not present in it."
)

ESCALATION_MESSAGE = (
    "That's outside what I can help with directly. The best next step is to book a call "
    "with a Cadre AI strategist, who can dig into specifics with you."
)


class ChatState(TypedDict, total=False):
    message: str
    intent: str
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
            max_tokens=100,
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": CLASSIFY_SCHEMA},
            },
            system=f"Classify the user's message into exactly one category:\n{INTENT_DESCRIPTIONS}",
            messages=[{"role": "user", "content": state["message"]}],
        )
        text = next(b.text for b in response.content if b.type == "text")
        intent = json.loads(text)["intent"]
    except Exception:
        logger.exception("classify failed, defaulting to out_of_scope")
        intent = "out_of_scope"
    logger.info("classify: intent=%s", intent)
    return {"intent": intent}


def answer(state: ChatState) -> ChatState:
    intent = state["intent"]
    keys = INTENT_KNOWLEDGE_KEYS.get(intent)
    if not keys:
        return {"draft_answer": None, "knowledge_used": []}

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
        logger.exception("answer failed for intent=%s", intent)
    logger.info("answer: intent=%s knowledge_used=%s ok=%s", intent, keys, draft is not None)
    return {"draft_answer": draft, "knowledge_used": keys}


def escalation_check(state: ChatState) -> ChatState:
    escalate = state["intent"] == "out_of_scope" or not state.get("draft_answer")
    logger.info("escalation_check: intent=%s escalate=%s", state["intent"], escalate)
    return {"escalate": escalate}


def respond(state: ChatState) -> ChatState:
    response = ESCALATION_MESSAGE if state["escalate"] else state["draft_answer"]
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
