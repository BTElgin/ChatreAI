import logging

import httpx

from app.config import LEAD_WEBHOOK_URL

logger = logging.getLogger("cadre_chat")

# Extracted by classify() on every turn (folded into its existing structured-output
# call rather than a separate one) so any name/business info a person volunteers —
# prospect or existing customer, asked or not — is picked up passively and can
# personalize the very next answer. Nothing here is ever solicited on its own;
# see LEAD_ASK_PROMPT below for the one place this project explicitly asks for info.
PROFILE_FIELDS = ["name", "business_name", "business_type", "phone", "email"]
PROFILE_SCHEMA_PROPERTIES = {field: {"type": "string"} for field in PROFILE_FIELDS}


def filter_profile(data: dict) -> dict:
    return {field: data[field] for field in PROFILE_FIELDS if data.get(field)}


# Three fixed, hand-authored strings (never LLM-generated) appended verbatim to the
# bot's response when each step happens. Because the frontend replays the full
# response back as history on the next turn, checking for these exact substrings
# in past assistant messages is a reliable, stateless way to know "have we already
# asked" / "has this already been delivered" without any server-side session
# store — the conversation transcript itself is the only state this project has.
LEAD_ASK_PROMPT = (
    "By the way, if it'd help to have someone from Cadre reach out directly, just share "
    "your name and the best email or phone to reach you (your business name too, if you "
    "want). No pressure either way."
)

LEAD_DELIVERED_NOTE = "Thanks, I've passed your details along to the Cadre team. Someone will reach out directly."

CUSTOMER_SIGNAL_NOTE = "Noted for your account team, so they have this context next time you're in touch."

BUYING_INTENT_TRIGGERS = {"booking", "pricing"}


def shows_buying_intent(intents: list[str]) -> bool:
    return bool(set(intents) & BUYING_INTENT_TRIGGERS)


def _history_contains(history: list[dict], marker: str) -> bool:
    return any(m.get("role") == "assistant" and marker in m.get("content", "") for m in history)


def already_asked(history: list[dict]) -> bool:
    return _history_contains(history, LEAD_ASK_PROMPT)


def already_delivered(history: list[dict], marker: str = LEAD_DELIVERED_NOTE) -> bool:
    return _history_contains(history, marker)


def is_lead_complete(profile: dict) -> bool:
    return bool(profile.get("name")) and bool(profile.get("email") or profile.get("phone"))


def is_customer_signal_worth_sending(profile: dict) -> bool:
    return bool(profile.get("name"))


def deliver_lead(profile: dict, context: dict) -> bool:
    """POST the profile to LEAD_WEBHOOK_URL. Returns whether delivery actually
    happened — callers must not tell the user their info was sent unless this is
    True, since no destination is configured until a real webhook URL is set
    (mirrors BOOKING_URL's placeholder-until-configured pattern)."""
    if not LEAD_WEBHOOK_URL:
        logger.info("profile ready but LEAD_WEBHOOK_URL not configured, skipping delivery: %s", profile)
        return False
    try:
        httpx.post(LEAD_WEBHOOK_URL, json={"lead": profile, **context}, timeout=5.0)
        logger.info("profile delivered via webhook: %s", profile)
        return True
    except Exception:
        logger.exception("profile webhook delivery failed")
        return False
