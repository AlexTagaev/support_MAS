"""Telegram must not call the model without a usable RAG result."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-only-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-only-token")

from app.integrations import telegram_bot


class FakeMessage:
    text = "Where can I find information?"

    def __init__(self, text=None):
        if text is not None:
            self.text = text


def test_message_is_deferred_until_index_exists(monkeypatch):
    monkeypatch.setattr(telegram_bot.rag, "index", None)
    send = AsyncMock(return_value=True)
    model = AsyncMock()
    monkeypatch.setattr(telegram_bot, "safe_answer", send)
    monkeypatch.setattr(telegram_bot.ai, "generate_response", model)

    asyncio.run(telegram_bot._process_message(FakeMessage(), "telegram_test_not_ready"))

    send.assert_awaited_once()
    model.assert_not_awaited()


def test_blank_message_is_ignored_without_calling_model(monkeypatch):
    monkeypatch.setattr(telegram_bot.rag, "index", object())
    send = AsyncMock(return_value=True)
    model = AsyncMock()
    monkeypatch.setattr(telegram_bot, "safe_answer", send)
    monkeypatch.setattr(telegram_bot.ai, "generate_response", model)

    asyncio.run(telegram_bot._process_message(FakeMessage("   "), "telegram_test_blank"))

    send.assert_not_awaited()
    model.assert_not_awaited()


def test_rag_failure_does_not_call_model_without_context(monkeypatch):
    monkeypatch.setattr(telegram_bot.rag, "index", object())
    monkeypatch.setattr(telegram_bot, "schedule_question_analytics", lambda _question: None)
    monkeypatch.setattr(
        telegram_bot.context_manager,
        "get_context",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        telegram_bot.rag,
        "get_context_for_query",
        AsyncMock(side_effect=RuntimeError("simulated RAG failure")),
    )
    send = AsyncMock(return_value=True)
    model = AsyncMock()
    monkeypatch.setattr(telegram_bot, "safe_answer", send)
    monkeypatch.setattr(telegram_bot.ai, "generate_response", model)

    asyncio.run(telegram_bot._process_message(FakeMessage(), "telegram_test_rag_failure"))

    send.assert_awaited_once()
    model.assert_not_awaited()


def test_empty_rag_result_does_not_call_model(monkeypatch):
    monkeypatch.setattr(telegram_bot.rag, "index", object())
    monkeypatch.setattr(telegram_bot, "schedule_question_analytics", lambda _question: None)
    monkeypatch.setattr(
        telegram_bot.context_manager,
        "get_context",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        telegram_bot.rag,
        "get_context_for_query",
        AsyncMock(return_value=""),
    )
    send = AsyncMock(return_value=True)
    model = AsyncMock()
    monkeypatch.setattr(telegram_bot, "safe_answer", send)
    monkeypatch.setattr(telegram_bot.ai, "generate_response", model)

    asyncio.run(telegram_bot._process_message(FakeMessage(), "telegram_test_empty_context"))

    send.assert_awaited_once()
    model.assert_not_awaited()


def test_conversation_keys_separate_private_and_group_history():
    user = SimpleNamespace(id=42)
    private = SimpleNamespace(from_user=user, chat=SimpleNamespace(id=42))
    group = SimpleNamespace(from_user=user, chat=SimpleNamespace(id=-100123))

    assert telegram_bot.conversation_key(private) != telegram_bot.conversation_key(group)
