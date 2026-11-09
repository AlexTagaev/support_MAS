"""Migration command checks selected-provider handling without API calls."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

os.environ.setdefault("OPENAI_API_KEY", "test-only-key")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:test-only-token")

import migrate_embeddings as migration


def test_migration_uses_selected_provider_and_closes_clients(monkeypatch):
    rebuild = AsyncMock(return_value=True)
    verify = AsyncMock(return_value=True)
    close_clients = AsyncMock()
    monkeypatch.setattr(migration, "provider_credentials", lambda: ("test-proxi-key", "https://proxy.test/v1"))
    monkeypatch.setattr(migration, "migrate_embeddings", rebuild)
    monkeypatch.setattr(migration, "verify_migration", verify)
    monkeypatch.setattr(migration, "close_async_clients", close_clients)

    assert asyncio.run(migration.main()) is True
    rebuild.assert_awaited_once()
    verify.assert_awaited_once()
    close_clients.assert_awaited_once()


def test_missing_selected_provider_key_fails_before_rebuild(monkeypatch):
    rebuild = AsyncMock()
    monkeypatch.setattr(migration, "provider_credentials", lambda: ("", "https://proxy.test/v1"))
    monkeypatch.setattr(migration, "migrate_embeddings", rebuild)

    assert asyncio.run(migration.main()) is False
    rebuild.assert_not_awaited()


def test_index_verification_does_not_send_sample_queries(monkeypatch):
    fake_rag = SimpleNamespace(
        index=SimpleNamespace(ntotal=2),
        metadata=[{}, {}],
        search=AsyncMock(),
    )
    monkeypatch.setattr(migration, "RAGEngine", lambda *_args: fake_rag)

    assert asyncio.run(migration.verify_migration()) is True
    fake_rag.search.assert_not_awaited()
