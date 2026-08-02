import json
from unittest.mock import MagicMock

import pytest


def make_text_response(text: str) -> MagicMock:
    """Build a fake anthropic Message response carrying a single text block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


def classify_response(intents, has_unaddressed_scope=False, existing_customer=False) -> MagicMock:
    return make_text_response(
        json.dumps(
            {
                "intents": intents,
                "has_unaddressed_scope": has_unaddressed_scope,
                "existing_customer": existing_customer,
            }
        )
    )


def suggestions_response(suggestions) -> MagicMock:
    return make_text_response(json.dumps({"suggestions": suggestions}))


def lead_response(name="", business_name="", business_type="", phone="", email="") -> MagicMock:
    return make_text_response(
        json.dumps(
            {
                "name": name,
                "business_name": business_name,
                "business_type": business_type,
                "phone": phone,
                "email": email,
            }
        )
    )


@pytest.fixture
def mock_client(monkeypatch):
    """Replace app.graph's Anthropic client with a MagicMock — no live API key or tokens."""
    client = MagicMock()
    monkeypatch.setattr("app.graph._client", lambda: client)
    return client
