import json

from fastapi.testclient import TestClient

from app.config import BOOKING_URL
from app.graph import ESCALATION_CTA, ESCALATION_MESSAGE, STARTER_PROMPTS
from app.main import app
from conftest import make_text_response

client = TestClient(app)


def classify_response(intents, has_unaddressed_scope=False):
    return make_text_response(json.dumps({"intents": intents, "has_unaddressed_scope": has_unaddressed_scope}))


def suggestions_response(suggestions):
    return make_text_response(json.dumps({"suggestions": suggestions}))


def post(messages):
    return client.post("/api/chat", json={"messages": messages})


# --- config ---


def test_config_returns_the_booking_url_and_starter_prompts():
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"bookingUrl": BOOKING_URL, "starterPrompts": STARTER_PROMPTS}


def test_escalation_cta_is_a_markdown_link_to_the_booking_url():
    assert f"]({BOOKING_URL})" in ESCALATION_CTA
    assert f"]({BOOKING_URL})" in ESCALATION_MESSAGE


# --- the 6 core scenarios (classify/answer mocked; see CLAUDE.md for the real, unmocked pass) ---


def test_scenario_about_and_industries(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["about_and_industries"]),
        make_text_response("Cadre AI is a consultancy that works with real estate, too."),
    ]
    response = post([{"role": "user", "text": "What does Cadre AI do, and do you work with real estate?"}])
    assert response.status_code == 200
    assert response.json()["message"] == "Cadre AI is a consultancy that works with real estate, too."


def test_scenario_booking(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["booking"]),
        make_text_response("Book a call from the website."),
    ]
    response = post([{"role": "user", "text": "How do I book a call with an AI strategist?"}])
    assert response.status_code == 200
    assert response.json()["message"] == "Book a call from the website."


def test_scenario_client_portal(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["client_portal"]),
        make_text_response("The portal lives at portal.cadreai.com."),
    ]
    response = post([{"role": "user", "text": "How do I access the client portal?"}])
    assert response.status_code == 200
    assert "portal.cadreai.com" in response.json()["message"]


def test_scenario_ai_maturity_index(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["ai_maturity_index"]),
        make_text_response("The AI Maturity Index scores you on four tiers."),
    ]
    response = post([{"role": "user", "text": "What's the AI Maturity Index and how do I get scored?"}])
    assert response.status_code == 200
    assert "four tiers" in response.json()["message"]


def test_scenario_llm_and_data_security(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["llm_and_data_security"]),
        make_text_response("We're model-agnostic and never train on client data."),
    ]
    response = post([{"role": "user", "text": "How do you decide which LLM to use, and how do you handle data security?"}])
    assert response.status_code == 200
    assert "model-agnostic" in response.json()["message"]


def test_scenario_out_of_scope_escalates(mock_client):
    mock_client.messages.create.return_value = classify_response([], has_unaddressed_scope=True)
    response = post([{"role": "user", "text": "What's a good chocolate chip cookie recipe?"}])
    assert response.status_code == 200
    assert response.json()["message"] == ESCALATION_MESSAGE


# --- new intents: pricing, case studies ---


def test_scenario_pricing(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["pricing"]),
        make_text_response("Pricing is scoped per engagement — no fixed rate card."),
    ]
    response = post([{"role": "user", "text": "What do your services cost?"}])
    assert response.status_code == 200
    assert "scoped per engagement" in response.json()["message"]


def test_scenario_case_studies(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["case_studies"]),
        make_text_response("We've saved clients thousands of hours — here are a few examples."),
    ]
    response = post([{"role": "user", "text": "Do you have case studies?"}])
    assert response.status_code == 200
    assert "examples" in response.json()["message"]


# --- Phase 3 edge cases ---


def test_multi_part_question_merges_knowledge(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["about_and_industries", "booking"]),
        make_text_response("We're a consultancy, and here's how to book."),
    ]
    response = post([{"role": "user", "text": "What does Cadre AI do, and how do I book a call?"}])
    assert response.status_code == 200
    assert response.json()["message"] == "We're a consultancy, and here's how to book."


def test_partially_in_scope_question_appends_escalation_note(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["booking"], has_unaddressed_scope=True),
        make_text_response("Here's how to book a call."),
    ]
    response = post([{"role": "user", "text": "How do I book a call, and what do you charge?"}])
    body = response.json()["message"]
    assert body.startswith("Here's how to book a call.")
    assert ESCALATION_CTA in body


def test_ambiguous_message_escalates(mock_client):
    mock_client.messages.create.return_value = classify_response([], has_unaddressed_scope=True)
    response = post([{"role": "user", "text": "can you help me with that thing we talked about"}])
    assert response.status_code == 200
    assert response.json()["message"] == ESCALATION_MESSAGE


def test_simulated_api_failure_falls_back_to_escalation(mock_client):
    mock_client.messages.create.side_effect = RuntimeError("simulated outage")
    response = post([{"role": "user", "text": "anything"}])
    assert response.status_code == 200
    assert response.json()["message"] == ESCALATION_MESSAGE


def test_unexpected_endpoint_error_falls_back_gracefully(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("something broke outside the graph nodes")

    monkeypatch.setattr("app.main.run_chat", boom)
    response = post([{"role": "user", "text": "anything"}])
    assert response.status_code == 200
    assert response.json() == {"message": ESCALATION_MESSAGE, "suggestions": []}


# --- request validation ---


def test_rejects_empty_messages():
    response = post([])
    assert response.status_code == 400


def test_rejects_a_request_not_ending_in_a_user_message():
    response = post([{"role": "assistant", "text": "hi there"}])
    assert response.status_code == 400


# --- multi-turn history (Phase 5) ---


def test_history_is_threaded_through_to_the_model(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["about_and_industries"]),
        make_text_response("Yes, we work with real estate too."),
    ]
    response = post(
        [
            {"role": "user", "text": "What does Cadre AI do?"},
            {"role": "assistant", "text": "We are a consultancy."},
            {"role": "user", "text": "what about real estate?"},
        ]
    )
    assert response.status_code == 200

    classify_call = mock_client.messages.create.call_args_list[0]
    sent_messages = classify_call.kwargs["messages"]
    assert len(sent_messages) == 3
    assert sent_messages[-1] == {"role": "user", "content": "what about real estate?"}


# --- quick-prompt follow-up suggestions ---


def test_response_includes_suggestions_from_the_model(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["booking"]),
        make_text_response("Here's how to book a call."),
        suggestions_response(["What's the AI Maturity Index?", "Do you have case studies?"]),
    ]
    response = post([{"role": "user", "text": "How do I book a call?"}])
    assert response.status_code == 200
    assert response.json()["suggestions"] == ["What's the AI Maturity Index?", "Do you have case studies?"]


def test_suggestions_default_to_empty_list_when_generation_fails(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["booking"]),
        make_text_response("Here's how to book a call."),
        RuntimeError("suggestion model unavailable"),
    ]
    response = post([{"role": "user", "text": "How do I book a call?"}])
    assert response.status_code == 200
    assert response.json()["message"] == "Here's how to book a call."
    assert response.json()["suggestions"] == []


# --- model routing ---


def test_classify_and_answer_use_different_models(mock_client):
    from app.graph import ANSWER_MODEL, CLASSIFY_MODEL

    mock_client.messages.create.side_effect = [
        classify_response(["booking"]),
        make_text_response("Here's how to book a call."),
        suggestions_response([]),
    ]
    post([{"role": "user", "text": "How do I book a call?"}])

    classify_call, answer_call, _ = mock_client.messages.create.call_args_list
    assert classify_call.kwargs["model"] == CLASSIFY_MODEL
    assert answer_call.kwargs["model"] == ANSWER_MODEL
    assert CLASSIFY_MODEL != ANSWER_MODEL
