import json

from app.config import BOOKING_URL
from app.graph import (
    ANSWER_MODEL,
    ANSWER_VOICE_CUSTOMER_ADDENDUM,
    ANSWER_VOICE_LEAD_PENDING_ADDENDUM,
    ANSWER_VOICE_PROSPECT_ADDENDUM,
    CLASSIFY_MODEL,
    ESCALATION_CTA,
    ESCALATION_MESSAGE,
    EXISTING_CUSTOMER_ESCALATION_CTA,
    EXISTING_CUSTOMER_GREETING_RESPONSE,
    GREETING_RESPONSE,
    HISTORY_WINDOW,
    INTENT_KNOWLEDGE_KEYS,
    INTENTS,
    KNOWN_INTENTS,
    LEAD_DELIVERY_FALLBACK_NOTE,
    MAX_SUGGESTIONS,
    PARTIAL_ESCALATION_NOTE,
    STARTER_PROMPTS,
    SUGGEST_MODEL,
    answer,
    classify,
    escalation_check,
    lead_capture,
    respond,
    run_chat,
    suggest_followups,
)
from app.lead import CUSTOMER_SIGNAL_NOTE, LEAD_ASK_PROMPT, LEAD_DELIVERED_NOTE
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
        json.dumps(
            {
                "intents": ["booking", "made_up_intent"],
                "has_unaddressed_scope": False,
                "existing_customer": False,
                "is_greeting": False,
            }
        )
    )
    result = classify({"message": "anything", "history": []})
    assert result["intents"] == ["booking"]


def test_classify_defaults_to_escalate_on_api_failure(mock_client):
    mock_client.messages.create.side_effect = RuntimeError("boom")
    result = classify({"message": "anything", "history": []})
    assert result["intents"] == []
    assert result["has_unaddressed_scope"] is True
    assert result["existing_customer"] is False


def test_classify_flags_existing_customer(mock_client):
    mock_client.messages.create.return_value = classify_response(["client_portal"], existing_customer=True)
    result = classify({"message": "my AI agent isn't responding, how do I check on it?", "history": []})
    assert result["existing_customer"] is True


def test_classify_defaults_existing_customer_to_false(mock_client):
    mock_client.messages.create.return_value = classify_response(["booking"])
    result = classify({"message": "How do I book a call?", "history": []})
    assert result["existing_customer"] is False


def test_classify_flags_a_bare_greeting(mock_client):
    mock_client.messages.create.return_value = classify_response([], is_greeting=True)
    result = classify({"message": "hi", "history": []})
    assert result["is_greeting"] is True


def test_classify_defaults_is_greeting_to_false(mock_client):
    mock_client.messages.create.return_value = classify_response(["booking"])
    result = classify({"message": "How do I book a call?", "history": []})
    assert result["is_greeting"] is False


def test_classify_defaults_is_greeting_to_false_on_api_failure(mock_client):
    mock_client.messages.create.side_effect = RuntimeError("boom")
    result = classify({"message": "hi", "history": []})
    assert result["is_greeting"] is False


def test_classify_passively_extracts_a_volunteered_profile(mock_client):
    mock_client.messages.create.return_value = classify_response(
        ["pricing"], name="Jamie", business_name="Acme", email="jamie@example.com"
    )
    result = classify({"message": "I'm Jamie from Acme, what's your pricing?", "history": []})
    assert result["profile"] == {"name": "Jamie", "business_name": "Acme", "email": "jamie@example.com"}


def test_classify_defaults_profile_to_empty_when_nothing_volunteered(mock_client):
    mock_client.messages.create.return_value = classify_response(["pricing"])
    result = classify({"message": "what's your pricing?", "history": []})
    assert result["profile"] == {}


def test_classify_defaults_profile_to_empty_on_api_failure(mock_client):
    mock_client.messages.create.side_effect = RuntimeError("boom")
    result = classify({"message": "I'm Jamie", "history": []})
    assert result["profile"] == {}


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


def test_answer_uses_the_prospect_voice_by_default(mock_client):
    mock_client.messages.create.return_value = make_text_response("answer")
    answer({"message": "...", "intents": ["booking"], "history": []})
    system = mock_client.messages.create.call_args.kwargs["system"]
    assert ANSWER_VOICE_PROSPECT_ADDENDUM in system
    assert ANSWER_VOICE_CUSTOMER_ADDENDUM not in system


def test_answer_uses_the_customer_voice_for_existing_customers(mock_client):
    mock_client.messages.create.return_value = make_text_response("answer")
    answer({"message": "...", "intents": ["booking"], "history": [], "existing_customer": True})
    system = mock_client.messages.create.call_args.kwargs["system"]
    assert ANSWER_VOICE_CUSTOMER_ADDENDUM in system
    assert ANSWER_VOICE_PROSPECT_ADDENDUM not in system


def test_answer_tells_the_model_not_to_promise_followup_while_a_lead_is_pending(mock_client):
    # Regression test: without this, answer() (which has no idea lead_capture
    # exists) would naturally write "someone will follow up" on its own, directly
    # contradicting lead_capture's own confirmation/fallback appended right after.
    mock_client.messages.create.return_value = make_text_response("answer")
    history = [{"role": "assistant", "content": f"Sure. {LEAD_ASK_PROMPT}"}]
    answer({"message": "I'm Jamie, jamie@example.com", "intents": ["pricing"], "history": history})
    system = mock_client.messages.create.call_args.kwargs["system"]
    assert ANSWER_VOICE_LEAD_PENDING_ADDENDUM in system


def test_answer_omits_the_lead_pending_note_once_already_delivered(mock_client):
    mock_client.messages.create.return_value = make_text_response("answer")
    history = [{"role": "assistant", "content": f"Thanks. {LEAD_DELIVERED_NOTE}"}]
    answer({"message": "anything else?", "intents": ["pricing"], "history": history})
    system = mock_client.messages.create.call_args.kwargs["system"]
    assert ANSWER_VOICE_LEAD_PENDING_ADDENDUM not in system


def test_answer_omits_the_lead_pending_note_before_the_lead_has_been_asked(mock_client):
    mock_client.messages.create.return_value = make_text_response("answer")
    answer({"message": "what does it cost", "intents": ["pricing"], "history": []})
    system = mock_client.messages.create.call_args.kwargs["system"]
    assert ANSWER_VOICE_LEAD_PENDING_ADDENDUM not in system


def test_answer_personalizes_using_the_extracted_name(mock_client):
    mock_client.messages.create.return_value = make_text_response("answer")
    answer(
        {
            "message": "what does it cost",
            "intents": ["pricing"],
            "history": [],
            "profile": {"name": "Jamie"},
        }
    )
    system = mock_client.messages.create.call_args.kwargs["system"]
    assert "Jamie" in system


def test_answer_does_not_mention_a_name_when_none_was_extracted(mock_client):
    mock_client.messages.create.return_value = make_text_response("answer")
    answer({"message": "what does it cost", "intents": ["pricing"], "history": [], "profile": {}})
    system = mock_client.messages.create.call_args.kwargs["system"]
    assert "person's name is" not in system


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


# --- lead_capture ---


def _lead_state(**overrides):
    state = {
        "message": "what does it cost",
        "history": [],
        "intents": ["pricing"],
        "has_unaddressed_scope": False,
        "escalate": False,
        "existing_customer": False,
        "response": "Pricing is scoped per engagement.",
        "profile": {},
    }
    state.update(overrides)
    return state


_PRIOR_EXCHANGE = [
    {"role": "user", "content": "hi"},
    {"role": "assistant", "content": "hello, how can I help?"},
]


def test_lead_capture_skips_when_escalating(mock_client):
    result = lead_capture(_lead_state(history=_PRIOR_EXCHANGE, escalate=True, intents=[]))
    assert result == {}
    mock_client.messages.create.assert_not_called()


def test_lead_capture_skips_when_has_unaddressed_scope(mock_client):
    result = lead_capture(_lead_state(history=_PRIOR_EXCHANGE, has_unaddressed_scope=True))
    assert result == {}
    mock_client.messages.create.assert_not_called()


def test_lead_capture_does_not_ask_on_the_first_message(mock_client):
    result = lead_capture(_lead_state(history=[]))
    assert result == {}
    mock_client.messages.create.assert_not_called()


def test_lead_capture_does_not_ask_without_buying_intent(mock_client):
    result = lead_capture(_lead_state(history=_PRIOR_EXCHANGE, intents=["about_and_industries"]))
    assert result == {}
    mock_client.messages.create.assert_not_called()


def test_lead_capture_asks_when_buying_intent_and_a_prior_exchange_exist(mock_client):
    result = lead_capture(_lead_state(history=_PRIOR_EXCHANGE))
    assert LEAD_ASK_PROMPT in result["response"]
    assert result["response"].startswith("Pricing is scoped per engagement.")
    mock_client.messages.create.assert_not_called()


def test_lead_capture_does_nothing_once_already_delivered(mock_client):
    history = [{"role": "assistant", "content": f"Thanks. {LEAD_DELIVERED_NOTE}"}]
    result = lead_capture(_lead_state(history=history))
    assert result == {}
    mock_client.messages.create.assert_not_called()


def test_lead_capture_leaves_the_response_unchanged_when_the_profile_is_still_incomplete(mock_client):
    history = [{"role": "assistant", "content": f"Sure. {LEAD_ASK_PROMPT}"}]
    result = lead_capture(_lead_state(history=history, profile={"name": "Jamie"}))
    assert result == {}
    mock_client.messages.create.assert_not_called()


def test_lead_capture_delivers_and_confirms_when_the_profile_is_complete(mock_client, monkeypatch):
    monkeypatch.setattr("app.graph.lead.deliver_lead", lambda profile, context: True)
    history = [{"role": "assistant", "content": f"Sure. {LEAD_ASK_PROMPT}"}]
    result = lead_capture(_lead_state(history=history, profile={"name": "Jamie", "email": "jamie@example.com"}))
    assert LEAD_DELIVERED_NOTE in result["response"]
    mock_client.messages.create.assert_not_called()


def test_lead_capture_falls_back_when_delivery_is_not_configured_or_fails(mock_client, monkeypatch):
    monkeypatch.setattr("app.graph.lead.deliver_lead", lambda profile, context: False)
    history = [{"role": "assistant", "content": f"Sure. {LEAD_ASK_PROMPT}"}]
    result = lead_capture(_lead_state(history=history, profile={"name": "Jamie", "email": "jamie@example.com"}))
    assert LEAD_DELIVERY_FALLBACK_NOTE in result["response"]
    assert LEAD_DELIVERED_NOTE not in result["response"]


# --- lead_capture: existing-customer signal ---


def test_lead_capture_sends_no_signal_for_an_existing_customer_with_no_name(mock_client):
    result = lead_capture(_lead_state(existing_customer=True, profile={"business_name": "Acme"}))
    assert result == {}
    mock_client.messages.create.assert_not_called()


def test_lead_capture_delivers_a_signal_for_an_existing_customer_who_volunteered_a_name(mock_client, monkeypatch):
    monkeypatch.setattr("app.graph.lead.deliver_lead", lambda profile, context: True)
    result = lead_capture(_lead_state(existing_customer=True, profile={"name": "Jamie"}))
    assert CUSTOMER_SIGNAL_NOTE in result["response"]
    mock_client.messages.create.assert_not_called()


def test_lead_capture_stays_silent_for_an_existing_customer_when_delivery_is_not_configured(mock_client, monkeypatch):
    # Passive, never asked -- no promise was made, so unlike the prospect flow
    # there's no honest-fallback note owed here, just silence.
    monkeypatch.setattr("app.graph.lead.deliver_lead", lambda profile, context: False)
    result = lead_capture(_lead_state(existing_customer=True, profile={"name": "Jamie"}))
    assert result == {}


def test_lead_capture_does_not_resend_the_customer_signal_once_already_delivered(mock_client, monkeypatch):
    monkeypatch.setattr("app.graph.lead.deliver_lead", lambda profile, context: True)
    history = [{"role": "assistant", "content": f"Sure. {CUSTOMER_SIGNAL_NOTE}"}]
    result = lead_capture(_lead_state(existing_customer=True, history=history, profile={"name": "Jamie"}))
    assert result == {}


def test_lead_capture_never_asks_an_existing_customer_for_contact_info(mock_client):
    # Even with buying intent and a prior exchange, existing customers must never
    # get the explicit prospect ask -- only passive pickup applies to them.
    result = lead_capture(_lead_state(existing_customer=True, history=_PRIOR_EXCHANGE, profile={}))
    assert result == {}
    assert "response" not in result


def test_run_chat_lead_capture_full_flow_across_turns(mock_client, monkeypatch):
    monkeypatch.setattr("app.graph.lead.deliver_lead", lambda profile, context: True)

    # Turn 2: there's already one prior exchange in history, and this message
    # shows buying intent (pricing) — the answer should get the ask appended.
    mock_client.messages.create.side_effect = [
        classify_response(["pricing"]),
        make_text_response("Pricing is scoped per engagement."),
        suggestions_response([]),
    ]
    history_after_turn_1 = [
        {"role": "user", "content": "What does Cadre AI do?"},
        {"role": "assistant", "content": "Cadre AI is a consultancy."},
    ]
    turn_2 = run_chat("What do your services cost?", history_after_turn_1)
    assert LEAD_ASK_PROMPT in turn_2["response"]

    # Turn 3: the user volunteers contact info in their reply — classify picks it
    # up as part of its normal call, the profile is complete, and the lead is
    # delivered without any extra API call from lead_capture itself (3 calls this
    # turn: classify, answer, suggest_followups — nothing extra for extraction).
    mock_client.messages.create.reset_mock()
    mock_client.messages.create.side_effect = [
        classify_response(["pricing"], name="Jamie", email="jamie@example.com"),
        make_text_response("Great, happy to help further."),
        suggestions_response([]),
    ]
    history_after_turn_2 = [
        *history_after_turn_1,
        {"role": "user", "content": "What do your services cost?"},
        {"role": "assistant", "content": turn_2["response"]},
    ]
    turn_3 = run_chat("I'm Jamie, jamie@example.com", history_after_turn_2)
    assert LEAD_DELIVERED_NOTE in turn_3["response"]
    assert mock_client.messages.create.call_count == 3


def test_run_chat_personalizes_and_sends_a_customer_signal_for_a_self_declared_customer(mock_client, monkeypatch):
    monkeypatch.setattr("app.graph.lead.deliver_lead", lambda profile, context: True)
    mock_client.messages.create.side_effect = [
        classify_response(["client_portal"], existing_customer=True, name="Jamie"),
        make_text_response("Here's how to check your agent's status."),
        suggestions_response([]),
    ]
    result = run_chat("I'm Jamie -- my AI agent isn't responding, how do I check on it?")
    answer_call = mock_client.messages.create.call_args_list[1]
    assert "Jamie" in answer_call.kwargs["system"]
    assert CUSTOMER_SIGNAL_NOTE in result["response"]


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


def test_about_and_industries_covers_existing_customer_expansion_questions():
    # Regression test: "I'd love to improve my current Cadre AI plan" used to fall
    # through every intent (nothing matched "improve my plan" literally) and escalate
    # before answer()'s existing-customer voice ever got a chance to run, even though
    # the services knowledge this intent already carries is exactly the right content
    # to answer with. The description needs to explicitly invite that phrasing.
    assert "existing client" in INTENTS["about_and_industries"]["description"]


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


def test_escalation_check_does_not_escalate_on_a_bare_greeting():
    result = escalation_check({"intents": [], "has_unaddressed_scope": True, "is_greeting": True})
    assert result["escalate"] is False


def test_escalation_check_does_not_treat_a_matched_intent_as_greeting_only():
    # Guards the not-intents half of _is_greeting_only: even if classify ever set
    # is_greeting=True alongside a real matched intent (e.g. "hi, how do I book a
    # call?"), a matched intent means there's a real answer to give, so this must
    # follow the normal answer path, not the bare-greeting shortcut.
    result = escalation_check(
        {"intents": ["booking"], "has_unaddressed_scope": False, "is_greeting": True, "draft_answer": "text"}
    )
    assert result["escalate"] is False


# --- respond ---


def test_respond_returns_the_standard_escalation_message():
    result = respond({"escalate": True})
    assert result["response"] == ESCALATION_MESSAGE


def test_respond_returns_a_friendly_greeting_instead_of_escalating():
    result = respond({"escalate": True, "intents": [], "is_greeting": True})
    assert result["response"] == GREETING_RESPONSE


def test_respond_returns_the_customer_greeting_for_existing_customers():
    result = respond({"escalate": True, "intents": [], "is_greeting": True, "existing_customer": True})
    assert result["response"] == EXISTING_CUSTOMER_GREETING_RESPONSE


def test_respond_does_not_treat_a_matched_intent_as_greeting_only():
    result = respond(
        {"escalate": False, "intents": ["booking"], "is_greeting": True, "draft_answer": "Here you go.", "has_unaddressed_scope": False}
    )
    assert result["response"] == "Here you go."


def test_respond_returns_the_draft_answer_unchanged_when_fully_in_scope():
    result = respond({"escalate": False, "draft_answer": "Here you go.", "has_unaddressed_scope": False})
    assert result["response"] == "Here you go."


def test_respond_appends_the_partial_escalation_note():
    result = respond({"escalate": False, "draft_answer": "Here you go.", "has_unaddressed_scope": True})
    assert result["response"] == f"Here you go.{PARTIAL_ESCALATION_NOTE}"


def test_respond_routes_existing_customers_to_their_engagement_lead_on_full_escalation():
    result = respond({"escalate": True, "existing_customer": True})
    assert EXISTING_CUSTOMER_ESCALATION_CTA in result["response"]
    assert ESCALATION_CTA not in result["response"]


def test_respond_routes_existing_customers_to_their_engagement_lead_on_partial_escalation():
    result = respond(
        {
            "escalate": False,
            "draft_answer": "Here you go.",
            "has_unaddressed_scope": True,
            "existing_customer": True,
        }
    )
    assert EXISTING_CUSTOMER_ESCALATION_CTA in result["response"]
    assert ESCALATION_CTA not in result["response"]


# --- run_chat (full graph) ---


def test_run_chat_answers_an_in_scope_question(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["booking"]),
        make_text_response("Book a call from the website."),
    ]
    result = run_chat("How do I book a call?")
    assert result["response"] == "Book a call from the website."


def test_run_chat_greets_back_a_bare_greeting_instead_of_escalating(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response([], has_unaddressed_scope=True, is_greeting=True),
        suggestions_response([]),
    ]
    result = run_chat("hi")
    assert result["response"] == GREETING_RESPONSE
    # answer() must not call the model for a bare greeting either (no intents matched)
    assert mock_client.messages.create.call_count == 2


def test_run_chat_escalates_out_of_scope_questions(mock_client):
    mock_client.messages.create.return_value = classify_response([], has_unaddressed_scope=True)
    result = run_chat("What's a good cookie recipe?")
    assert result["response"] == ESCALATION_MESSAGE
    # answer() must not call the model when nothing was classified, but
    # suggest_followups always runs (classify + suggest_followups = 2 calls)
    assert mock_client.messages.create.call_count == 2


def test_run_chat_propagates_existing_customer_into_the_answer_voice(mock_client):
    mock_client.messages.create.side_effect = [
        classify_response(["client_portal"], existing_customer=True),
        make_text_response("Here's how to check your agent's status."),
    ]
    run_chat("my AI agent isn't responding, how do I check on it?")
    answer_call = mock_client.messages.create.call_args_list[1]
    assert ANSWER_VOICE_CUSTOMER_ADDENDUM in answer_call.kwargs["system"]


def test_run_chat_routes_existing_customers_to_their_engagement_lead_on_partial_escalation(mock_client):
    # Regression test: an existing customer's answer used to get a well-tailored,
    # customer-framed response that was then undercut by a generic prospect-facing
    # "book a call with a Cadre AI strategist" tail whenever has_unaddressed_scope
    # was also true — jarring and self-contradictory in production.
    mock_client.messages.create.side_effect = [
        classify_response(["client_portal"], has_unaddressed_scope=True, existing_customer=True),
        make_text_response("Here's how to check your agent's status."),
    ]
    result = run_chat("I already use Cadre — how do I check on my agent, and also what's a good cookie recipe?")
    assert EXISTING_CUSTOMER_ESCALATION_CTA in result["response"]
    assert ESCALATION_CTA not in result["response"]


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
