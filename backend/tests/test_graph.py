import json

from app.config import BOOKING_URL
from app.graph import (
    ANSWER_MODEL,
    CLASSIFY_MODEL,
    ESCALATION_MESSAGE,
    HISTORY_WINDOW,
    INTENT_KNOWLEDGE_KEYS,
    KNOWN_INTENTS,
    MAX_SUGGESTIONS,
    PARTIAL_ESCALATION_NOTE,
    STARTER_PROMPTS,
    SUGGEST_MODEL,
    answer,
    classify,
    escalation_check,
    respond,
    run_chat,
    suggest_followups,
)
from app.prompt import load_knowledge
from conftest import classify_response, make_text_response, suggestions_response


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


def test_answer_scopes_knowledge_for_pricing(mock_client):
    mock_client.messages.create.return_value = make_text_response("Pricing is scoped per engagement.")
    result = answer({"message": "what do you charge", "intents": ["pricing"], "history": []})
    assert result["knowledge_used"] == ["pricing"]


def test_answer_scopes_knowledge_for_case_studies(mock_client):
    mock_client.messages.create.return_value = make_text_response("Here are a few results.")
    result = answer({"message": "any case studies?", "intents": ["case_studies"], "history": []})
    assert result["knowledge_used"] == ["case_studies"]


# --- model routing ---


def test_classify_uses_the_cheap_model(mock_client):
    mock_client.messages.create.return_value = classify_response(["booking"])
    classify({"message": "How do I book?", "history": []})
    assert mock_client.messages.create.call_args.kwargs["model"] == CLASSIFY_MODEL


def test_answer_uses_the_full_model(mock_client):
    mock_client.messages.create.return_value = make_text_response("answer")
    answer({"message": "...", "intents": ["booking"], "history": []})
    assert mock_client.messages.create.call_args.kwargs["model"] == ANSWER_MODEL


def test_classify_and_answer_are_on_different_model_tiers():
    assert CLASSIFY_MODEL != ANSWER_MODEL


def test_classify_does_not_pass_effort_to_haiku(mock_client):
    # output_config.effort errors on Haiku 4.5 — classify must omit it.
    mock_client.messages.create.return_value = classify_response(["booking"])
    classify({"message": "How do I book?", "history": []})
    output_config = mock_client.messages.create.call_args.kwargs["output_config"]
    assert "effort" not in output_config


# --- suggest_followups ---


def test_suggest_followups_returns_suggestions_from_the_model(mock_client):
    mock_client.messages.create.return_value = suggestions_response(
        ["What's the AI Maturity Index?", "Do you have case studies?"]
    )
    result = suggest_followups({"message": "How do I book?", "history": [], "response": "Here's how to book."})
    assert result["suggestions"] == ["What's the AI Maturity Index?", "Do you have case studies?"]


def test_suggest_followups_caps_at_max_suggestions(mock_client):
    mock_client.messages.create.return_value = suggestions_response(
        [f"Question {i}?" for i in range(MAX_SUGGESTIONS + 5)]
    )
    result = suggest_followups({"message": "...", "history": [], "response": "answer"})
    assert len(result["suggestions"]) == MAX_SUGGESTIONS


def test_suggest_followups_returns_empty_list_on_api_failure(mock_client):
    mock_client.messages.create.side_effect = RuntimeError("boom")
    result = suggest_followups({"message": "...", "history": [], "response": "answer"})
    assert result["suggestions"] == []


def test_suggest_followups_uses_the_cheap_model(mock_client):
    mock_client.messages.create.return_value = suggestions_response([])
    suggest_followups({"message": "...", "history": [], "response": "answer"})
    assert mock_client.messages.create.call_args.kwargs["model"] == SUGGEST_MODEL


def test_suggest_followups_includes_the_response_in_context(mock_client):
    mock_client.messages.create.return_value = suggestions_response([])
    suggest_followups({"message": "How do I book?", "history": [], "response": "Here's how to book."})
    sent = mock_client.messages.create.call_args.kwargs["messages"]
    # Must end in a `user` message — structured outputs reject a trailing
    # `assistant` message as a disallowed prefill — so the exchange is folded
    # into the final user-role message instead of appended as its own turn.
    assert sent[-1]["role"] == "user"
    assert "How do I book?" in sent[-1]["content"]
    assert "Here's how to book." in sent[-1]["content"]


# --- starter prompts / known intents sanity checks ---


def test_starter_prompts_are_non_empty_strings():
    assert len(STARTER_PROMPTS) > 0
    assert all(isinstance(p, str) and p for p in STARTER_PROMPTS)


def test_pricing_and_case_studies_are_known_intents():
    assert "pricing" in KNOWN_INTENTS
    assert "case_studies" in KNOWN_INTENTS


def test_every_intent_knowledge_key_exists_in_the_knowledge_base():
    knowledge = load_knowledge()
    for intent, keys in INTENT_KNOWLEDGE_KEYS.items():
        for key in keys:
            assert key in knowledge, f"{intent} references missing knowledge key {key!r}"


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
    # answer() must not call the model when nothing was classified, but
    # suggest_followups always runs (classify + suggest_followups = 2 calls)
    assert mock_client.messages.create.call_count == 2


def test_run_chat_windows_long_history(mock_client):
    mock_client.messages.create.return_value = classify_response([], has_unaddressed_scope=True)
    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg{i}"} for i in range(30)
    ]
    run_chat("latest message", long_history)
    # First call is classify — inspect that one specifically, since suggest_followups
    # also calls the model afterward with a different (longer) messages list.
    sent = mock_client.messages.create.call_args_list[0].kwargs["messages"]
    # HISTORY_WINDOW caps the prior history; the current message is appended on top of that.
    assert len(sent) == HISTORY_WINDOW + 1
    assert sent[-1] == {"role": "user", "content": "latest message"}
    assert sent[0] == {"role": "user", "content": "msg10"}
