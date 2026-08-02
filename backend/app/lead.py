import json
import logging

import httpx

from app.config import LEAD_WEBHOOK_URL

logger = logging.getLogger("cadre_chat")

LEAD_MODEL = "claude-haiku-4-5"

# Two fixed, hand-authored strings (never LLM-generated) appended verbatim to the
# bot's response when each step happens. Because the frontend replays the full
# response back as history on the next turn, checking for these exact substrings
# in past assistant messages is a reliable, stateless way to know "have we already
# asked" / "has this lead already been delivered" without any server-side session
# store — the conversation transcript itself is the only state this project has.
LEAD_ASK_PROMPT = (
    "By the way, if it'd help to have someone from Cadre reach out directly, just share "
    "your name and the best email or phone to reach you, and your business name if you'd "
    "like — no pressure either way."
)

LEAD_DELIVERED_NOTE = "Thanks — I've passed your details along to the Cadre team, and someone will reach out directly."

LEAD_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "business_name": {"type": "string"},
        "business_type": {"type": "string"},
        "phone": {"type": "string"},
        "email": {"type": "string"},
    },
    "required": ["name", "business_name", "business_type", "phone", "email"],
    "additionalProperties": False,
}

LEAD_EXTRACT_SYSTEM = (
    "Extract any of the following the user has volunteered about themselves or their business, "
    "anywhere in this conversation: their name, business name, business type or category, phone "
    "number, and email address. Use an empty string for anything not mentioned. Only extract "
    "information the user actually stated — never invent, guess, or infer a value that wasn't given."
)

BUYING_INTENT_TRIGGERS = {"booking", "pricing"}


def shows_buying_intent(intents: list[str]) -> bool:
    return bool(set(intents) & BUYING_INTENT_TRIGGERS)


def _history_contains(history: list[dict], marker: str) -> bool:
    return any(m.get("role") == "assistant" and marker in m.get("content", "") for m in history)


def already_asked(history: list[dict]) -> bool:
    return _history_contains(history, LEAD_ASK_PROMPT)


def already_delivered(history: list[dict]) -> bool:
    return _history_contains(history, LEAD_DELIVERED_NOTE)


def parse_lead_response(text: str) -> dict:
    data = json.loads(text)
    return {k: v for k, v in data.items() if v}


def is_lead_complete(lead: dict) -> bool:
    return bool(lead.get("name")) and bool(lead.get("email") or lead.get("phone"))


def deliver_lead(lead: dict, context: dict) -> bool:
    """POST the completed lead to LEAD_WEBHOOK_URL. Returns whether delivery actually
    happened — callers must not tell the user their info was sent unless this is True,
    since no destination is configured until a real webhook URL is set (mirrors
    BOOKING_URL's placeholder-until-configured pattern)."""
    if not LEAD_WEBHOOK_URL:
        logger.info("lead ready but LEAD_WEBHOOK_URL not configured, skipping delivery: %s", lead)
        return False
    try:
        httpx.post(LEAD_WEBHOOK_URL, json={"lead": lead, **context}, timeout=5.0)
        logger.info("lead delivered via webhook: %s", lead)
        return True
    except Exception:
        logger.exception("lead webhook delivery failed")
        return False
