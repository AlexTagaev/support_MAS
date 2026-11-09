"""Focused RAG lifecycle tests; embeddings are mocked and never call a provider."""

import os

os.environ["OPENAI_API_KEY"] = "test-only-key"
os.environ["TELEGRAM_BOT_TOKEN"] = "123456:test-only-token"

import asyncio
from pathlib import Path

import pytest

from app.config import settings
from app.core.rag_engine import RAGEngine


def make_engine(tmp_path, text="## First\n\nalpha knowledge\n"):
    knowledge = tmp_path / "knowledge.md"
    knowledge.write_text(text, encoding="utf-8")
    engine = RAGEngine(str(knowledge), str(tmp_path / "index"))

    async def embed(self, _text):
        return [1.0, 0.0]

    engine._get_embedding = embed.__get__(engine, RAGEngine)
    return engine, knowledge


def test_chunks_respect_size_and_skip_structural_only_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHUNK_SIZE", 64)
    monkeypatch.setattr(settings, "CHUNK_OVERLAP", 16)
    engine, _ = make_engine(tmp_path, "# Title\n\n---\n\n" + ("word " * 50))

    chunks = engine._chunk_text(Path(engine.kb_path).read_text(encoding="utf-8"))

    assert chunks
    assert all(len(chunk) <= 64 for chunk in chunks)
    assert all(chunk.strip() != "---" for chunk in chunks)
    assert all(not (chunk.startswith("#") and "\n" not in chunk) for chunk in chunks)


def test_rebuild_rejects_empty_knowledge(tmp_path):
    engine, knowledge = make_engine(tmp_path, "   \n---\n### heading only\n")

    with pytest.raises(ValueError, match="empty"):
        asyncio.run(engine.rebuild_index())
    assert not (tmp_path / "index" / "CURRENT").exists()


def test_failed_rebuild_keeps_published_generation(tmp_path):
    engine, knowledge = make_engine(tmp_path)
    asyncio.run(engine.rebuild_index())
    current_before = (tmp_path / "index" / "CURRENT").read_text(encoding="ascii")
    old_index = engine.index
    old_metadata = list(engine.metadata)

    knowledge.write_text("## Changed\n\nnew text\n", encoding="utf-8")

    async def fail_embedding(_text):
        raise RuntimeError("simulated provider failure")

    engine._get_embedding = fail_embedding
    with pytest.raises(RuntimeError, match="simulated"):
        asyncio.run(engine.rebuild_index())

    assert (tmp_path / "index" / "CURRENT").read_text(encoding="ascii") == current_before
    assert engine.index is old_index
    assert engine.metadata == old_metadata


def test_rebuild_is_visible_to_existing_and_reloaded_engine(tmp_path):
    engine, knowledge = make_engine(tmp_path)
    asyncio.run(engine.rebuild_index())
    knowledge.write_text("## Updated\n\nupdated knowledge\n", encoding="utf-8")
    asyncio.run(engine.rebuild_index())

    reloaded = RAGEngine(str(knowledge), str(tmp_path / "index"))
    assert engine.metadata == reloaded.metadata
    assert "updated knowledge" in reloaded.metadata[0]["text"]
    assert engine.index.ntotal == len(engine.metadata)
    assert reloaded.index.ntotal == len(reloaded.metadata)


def test_search_uses_consistent_index_metadata_snapshot(tmp_path):
    engine, _ = make_engine(tmp_path)
    asyncio.run(engine.rebuild_index())

    async def search():
        return await engine.search("question", top_k=1)

    result = asyncio.run(search())
    assert result
    assert result[0]["metadata"] == engine.metadata[0]


def test_search_without_index_does_not_request_embedding(tmp_path):
    engine, _ = make_engine(tmp_path)

    async def unexpected_embedding(_text):
        raise AssertionError("embedding must not be requested without an index")

    engine._get_embedding = unexpected_embedding
    assert asyncio.run(engine.search("question")) == []
