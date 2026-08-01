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


@pytest.fixture
def mock_client(monkeypatch):
    """Replace app.graph's Anthropic client with a MagicMock — no live API key or tokens."""
    client = MagicMock()
    monkeypatch.setattr("app.graph._client", lambda: client)
    return client
