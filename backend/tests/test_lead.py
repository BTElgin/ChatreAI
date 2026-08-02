from unittest.mock import MagicMock

from app.lead import (
    CUSTOMER_SIGNAL_NOTE,
    LEAD_ASK_PROMPT,
    LEAD_DELIVERED_NOTE,
    already_asked,
    already_delivered,
    deliver_lead,
    filter_profile,
    is_customer_signal_worth_sending,
    is_lead_complete,
    shows_buying_intent,
)

# --- shows_buying_intent ---


def test_shows_buying_intent_true_for_booking():
    assert shows_buying_intent(["booking"]) is True


def test_shows_buying_intent_true_for_pricing():
    assert shows_buying_intent(["pricing"]) is True


def test_shows_buying_intent_false_for_unrelated_intents():
    assert shows_buying_intent(["about_and_industries", "client_portal"]) is False


def test_shows_buying_intent_false_for_empty_intents():
    assert shows_buying_intent([]) is False


# --- already_asked / already_delivered ---


def test_already_asked_detects_the_marker_in_history():
    history = [
        {"role": "user", "content": "what's pricing"},
        {"role": "assistant", "content": f"Pricing is scoped per engagement. {LEAD_ASK_PROMPT}"},
    ]
    assert already_asked(history) is True


def test_already_asked_false_when_marker_absent():
    history = [
        {"role": "user", "content": "what's pricing"},
        {"role": "assistant", "content": "Pricing is scoped per engagement."},
    ]
    assert already_asked(history) is False


def test_already_asked_ignores_user_messages_containing_similar_text():
    history = [{"role": "user", "content": LEAD_ASK_PROMPT}]
    assert already_asked(history) is False


def test_already_delivered_detects_the_lead_marker_by_default():
    history = [{"role": "assistant", "content": f"Thanks. {LEAD_DELIVERED_NOTE}"}]
    assert already_delivered(history) is True


def test_already_delivered_false_when_marker_absent():
    history = [{"role": "assistant", "content": "Thanks!"}]
    assert already_delivered(history) is False


def test_already_delivered_supports_a_custom_marker_for_the_customer_signal():
    history = [{"role": "assistant", "content": f"Noted. {CUSTOMER_SIGNAL_NOTE}"}]
    assert already_delivered(history, marker=CUSTOMER_SIGNAL_NOTE) is True
    # The lead-delivered marker shouldn't false-positive against the signal marker
    assert already_delivered(history) is False


# --- filter_profile ---


def test_filter_profile_drops_empty_strings():
    profile = filter_profile({"name": "Jamie", "business_name": "", "business_type": "", "phone": "", "email": ""})
    assert profile == {"name": "Jamie"}


def test_filter_profile_keeps_all_non_empty_fields():
    profile = filter_profile(
        {
            "name": "Jamie",
            "business_name": "Acme",
            "business_type": "retail",
            "phone": "555-1234",
            "email": "jamie@example.com",
        }
    )
    assert profile == {
        "name": "Jamie",
        "business_name": "Acme",
        "business_type": "retail",
        "phone": "555-1234",
        "email": "jamie@example.com",
    }


def test_filter_profile_ignores_unrelated_keys():
    # classify()'s response includes intents/has_unaddressed_scope/etc. alongside
    # the profile fields -- filter_profile must pick out only the profile ones.
    profile = filter_profile({"name": "Jamie", "intents": ["pricing"], "has_unaddressed_scope": False})
    assert profile == {"name": "Jamie"}


# --- is_lead_complete ---


def test_is_lead_complete_true_with_name_and_email():
    assert is_lead_complete({"name": "Jamie", "email": "jamie@example.com"}) is True


def test_is_lead_complete_true_with_name_and_phone():
    assert is_lead_complete({"name": "Jamie", "phone": "555-1234"}) is True


def test_is_lead_complete_false_without_a_name():
    assert is_lead_complete({"email": "jamie@example.com"}) is False


def test_is_lead_complete_false_without_any_contact_method():
    assert is_lead_complete({"name": "Jamie"}) is False


def test_is_lead_complete_false_when_empty():
    assert is_lead_complete({}) is False


# --- is_customer_signal_worth_sending ---


def test_is_customer_signal_worth_sending_true_with_just_a_name():
    assert is_customer_signal_worth_sending({"name": "Jamie"}) is True


def test_is_customer_signal_worth_sending_false_without_a_name():
    assert is_customer_signal_worth_sending({"business_name": "Acme"}) is False


def test_is_customer_signal_worth_sending_false_when_empty():
    assert is_customer_signal_worth_sending({}) is False


# --- deliver_lead ---


def test_deliver_lead_noops_and_returns_false_when_webhook_not_configured(monkeypatch):
    monkeypatch.setattr("app.lead.LEAD_WEBHOOK_URL", None)
    post = MagicMock()
    monkeypatch.setattr("app.lead.httpx.post", post)
    delivered = deliver_lead({"name": "Jamie", "email": "jamie@example.com"}, {"intents": ["pricing"]})
    assert delivered is False
    post.assert_not_called()


def test_deliver_lead_posts_to_the_webhook_and_returns_true_when_configured(monkeypatch):
    monkeypatch.setattr("app.lead.LEAD_WEBHOOK_URL", "https://example.com/webhook")
    post = MagicMock()
    monkeypatch.setattr("app.lead.httpx.post", post)
    profile = {"name": "Jamie", "email": "jamie@example.com"}
    delivered = deliver_lead(profile, {"intents": ["pricing"]})
    assert delivered is True
    post.assert_called_once()
    assert post.call_args.args[0] == "https://example.com/webhook"
    assert post.call_args.kwargs["json"] == {"lead": profile, "intents": ["pricing"]}


def test_deliver_lead_returns_false_on_post_failure(monkeypatch):
    monkeypatch.setattr("app.lead.LEAD_WEBHOOK_URL", "https://example.com/webhook")
    monkeypatch.setattr("app.lead.httpx.post", MagicMock(side_effect=RuntimeError("boom")))
    delivered = deliver_lead({"name": "Jamie", "email": "jamie@example.com"}, {"intents": []})
    assert delivered is False
