import json

from app.config import BOOKING_URL
from app.graph import (
    ESCALATION_MESSAGE,
    HISTORY_WINDOW,
    PARTIAL_ESCALATION_NOTE,
    answer,
    classify,
    escalation_check,
    respond,
    run_chat,
)
from app.prompt import load_knowledge
from conftest import make_text_response


def classify_response(intents, has_unaddressed_scope=False):
    return make_text_response(json.dumps({"intents": intents, "has_unaddressed_scope": has_unaddressed_scope}))


# --- knowledge loading ---


def test_load_knowledge_injects_the_booking_url():
    knowledge = load_knowledge()
    assert knowledge["booking"]["url"] == BOOKING_URL


# --- classify ---


def test_classify_returns_matched_intents(mock_client):
    mock_client.messages.create.return_value = classify_response(["booking"])
    result = classify({"message": "How do I book a call?", "history": []})
    assert result["intents"] == ["booking"]
    assert result["has_unaddressed_scope"] is False


def test_classify_supports_multiple_intents(mock_client):
    mock_client.messages.create.return_value = classify_response(["about_and_industries", "booking"])
    result = classify({"message": "What do you do, and how do I book a call?", "history": []})
    assert result["intents"] == ["about_and_industries", "booking"]


def test_classify_flags_unaddressed_scope(mock_client):
    mock_client.messages.create.return_value = classify_response(["booking"], has_unaddressed_scope=True)
    result = classify({"message": "How do I book, and what do you charge?", "history": []})
    assert result["has_unaddressed_scope"] is True


def test_classify_drops_unknown_intents_from_the_model(mock_client):
    mock_client.messages.create.return_value = make_text_response(
        json.dumps({"intents": ["booking", "made_up_intent"], "has_unaddressed_scope": False})
    )
    result = classify({"message": "anything", "history": []})
    assert result["intents"] == ["booking"]


def test_classify_defaults_to_escalate_on_api_failure(mock_client):
    mock_client.messages.create.side_effect = RuntimeError("boom")
    result = classify({"message": "anything", "history": []})
    assert result["intents"] == []
    assert result["has_unaddressed_scope"] is True


def test_classify_sends_history_and_latest_message(mock_client):
    mock_client.messages.create.return_value = classify_response(["about_and_industries"])
    history = [
        {"role": "user", "content": "What does Cadre AI do?"},
        {"role": "assistant", "content": "We are a consultancy."},
    ]
    classify({"message": "what about healthcare?", "history": history})
    sent = mock_client.messages.create.call_args.kwargs["messages"]
    assert sent == [*history, {"role": "user", "content": "what about healthcare?"}]


# --- answer ---


def test_answer_scopes_knowledge_to_matched_intents(mock_client):
    mock_client.messages.create.return_value = make_text_response("Cadre AI is a consultancy.")
    result = answer({"message": "what do you do", "intents": ["about_and_industries"], "history": []})
    assert result["draft_answer"] == "Cadre AI is a consultancy."
    assert set(result["knowledge_used"]) == {"company", "services", "industries_served"}


def test_answer_merges_knowledge_across_multiple_intents(mock_client):
    mock_client.messages.create.return_value = make_text_response("combined answer")
    result = answer({"message": "...", "intents": ["booking", "client_portal"], "history": []})
    assert result["knowledge_used"] == ["booking", "client_portal"]


def test_answer_skips_the_api_call_when_no_intents_matched(mock_client):
    result = answer({"message": "??", "intents": [], "history": []})
    assert result["draft_answer"] is None
    assert result["knowledge_used"] == []
    mock_client.messages.create.assert_not_called()


def test_answer_returns_none_on_api_failure(mock_client):
    mock_client.messages.create.side_effect = RuntimeError("boom")
    result = answer({"message": "...", "intents": ["booking"], "history": []})
    assert result["draft_answer"] is None


# --- escalation_check ---


def test_escalation_check_escalates_when_no_intents_matched():
    result = escalation_check({"intents": [], "has_unaddressed_scope": True})
    assert result["escalate"] is True


def test_escalation_check_escalates_when_answer_failed():
    result = escalation_check({"intents": ["booking"], "has_unaddressed_scope": False, "draft_answer": None})
    assert result["escalate"] is True


def test_escalation_check_does_not_escalate_on_a_grounded_answer():
    result = escalation_check({"intents": ["booking"], "has_unaddressed_scope": False, "draft_answer": "text"})
    assert result["escalate"] is False


# --- respond ---


def test_respond_returns_the_standard_escalation_message():
    result = respond({"escalate": True})
    assert result["response"] == ESCALATION_MESSAGE


def test_respond_returns_the_draft_answer_unchanged_when_fully_in_scope():
    result = respond({"escalate": False, "draft_answer": "Here you go.", "has_unaddressed_scope": False})
    assert result["response"] == "Here you go."


def test_respond_appends_the_partial_escalation_note():
    result = respond({"escalate": False, "draft_answer": "Here you go.", "has_unaddressed_scope": True})
    assert result["response"] == f"Here you go.{PARTIAL_ESCALATION_NOTE}"


# --- run_chat (full graph) ---


def test_run_chat_answers_an_in_scope_question(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["booking"]),
        make_text_response("Book a call from the website."),
    ]
    result = run_chat("How do I book a call?")
    assert result["response"] == "Book a call from the website."


def test_run_chat_escalates_out_of_scope_questions(mock_client):
    mock_client.messages.create.return_value = classify_response([], has_unaddressed_scope=True)
    result = run_chat("What's a good cookie recipe?")
    assert result["response"] == ESCALATION_MESSAGE
    # answer() must not call the model when nothing was classified
    assert mock_client.messages.create.call_count == 1


def test_run_chat_windows_long_history(mock_client):
    mock_client.messages.create.return_value = classify_response([], has_unaddressed_scope=True)
    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"} for i in range(30)
    ]
    run_chat("latest message", long_history)
    sent = mock_client.messages.create.call_args.kwargs["messages"]
    # HISTORY_WINDOW caps the prior history; the current message is appended on top of that.
    assert len(sent) == HISTORY_WINDOW + 1
    assert sent[-1] == {"role": "user", "content": "latest message"}
    assert sent[0] == {"role": "user", "content": "msg10"}
