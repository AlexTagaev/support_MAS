"""Provider client tests use mocks only and never send API requests."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import Mock

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-only-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-only-token")

from app.core import provider_clients
from app.core.ai_client import AIClient
from app.core.rag_engine import RAGEngine
from app.config import settings


@pytest.fixture(autouse=True)
def clear_client_cache():
    provider_clients._clients.clear()
    yield
    provider_clients._clients.clear()


def test_selected_proxiapi_client_is_reused(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "proxiapi")
    monkeypatch.setattr(settings, "PROXIAPI_API_KEY", "test-proxi-key")
    monkeypatch.setattr(settings, "PROXIAPI_API_BASE", "https://proxy.example/v1")
    client = object()
    factory = Mock(return_value=client)
    monkeypatch.setattr(provider_clients, "AsyncOpenAI", factory)

    assert provider_clients.get_async_client() is client
    assert provider_clients.get_async_client() is client
    factory.assert_called_once_with(
        api_key="test-proxi-key",
        timeout=30.0,
        max_retries=2,
        base_url="https://proxy.example/v1",
    )


def test_missing_selected_provider_key_fails_without_client_creation(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    factory = Mock()
    monkeypatch.setattr(provider_clients, "AsyncOpenAI", factory)

    with pytest.raises(ValueError, match="API key is not configured"):
        provider_clients.get_async_client()
    factory.assert_not_called()


def test_clients_close_on_shutdown(monkeypatch):
    clients = [SimpleAsyncClient(), SimpleAsyncClient()]
    provider_clients._clients.update({("key-1", None): clients[0], ("key-2", None): clients[1]})

    asyncio.run(provider_clients.close_async_clients())

    assert provider_clients._clients == {}
    for client in clients:
        client.close.assert_awaited_once()


class SimpleAsyncClient:
    def __init__(self):
        self.close = AsyncMock()


def test_ai_client_returns_chat_response_and_passes_context(monkeypatch):
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Answer"))])
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr("app.core.ai_client.get_async_client", lambda: client)

    result = asyncio.run(
        AIClient().generate_response(
            user_question="Question",
            rag_context="Relevant facts",
            conversation_history=[{"role": "user", "content": "Earlier question"}],
            system_prompt="Instructions",
        )
    )

    assert result == "Answer"
    args = create.await_args.kwargs
    assert args["model"] == settings.AI_MODEL
    assert args["max_tokens"] == settings.AI_MAX_TOKENS
    assert args["messages"][0] == {"role": "system", "content": "Instructions"}
    assert "Relevant facts" in args["messages"][1]["content"]
    assert {"role": "user", "content": "Earlier question"} in args["messages"]
    assert args["messages"][-1] == {"role": "user", "content": "Question"}


def test_ai_client_handles_timeout_and_malformed_response(monkeypatch):
    create = AsyncMock(side_effect=TimeoutError("simulated timeout"))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr("app.core.ai_client.get_async_client", lambda: client)
    timeout_result = asyncio.run(AIClient().generate_response("Q", "facts", [], "system"))
    assert "произошла ошибка" in timeout_result

    create.side_effect = None
    create.return_value = SimpleNamespace(choices=[])
    malformed_result = asyncio.run(AIClient().generate_response("Q", "facts", [], "system"))
    assert "произошла ошибка" in malformed_result


def test_cancellation_propagates_from_ai_client(monkeypatch):
    create = AsyncMock(side_effect=asyncio.CancelledError())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr("app.core.ai_client.get_async_client", lambda: client)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(AIClient().generate_response("Q", "facts", [], "system"))


def test_embedding_uses_shared_async_provider_client(monkeypatch, tmp_path):
    response = SimpleNamespace(data=[SimpleNamespace(embedding=[0.25, 0.75])])
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    monkeypatch.setattr("app.core.rag_engine.get_async_client", lambda: client)
    engine = RAGEngine(str(tmp_path / "kb.md"), str(tmp_path / "index"))

    result = asyncio.run(engine._get_embedding("input text"))

    assert result == [0.25, 0.75]
    create.assert_awaited_once_with(input="input text", model="text-embedding-3-small")
