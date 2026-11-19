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


def test_oversized_section_repeats_breadcrumb_and_preserves_code_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHUNK_SIZE", 100)
    monkeypatch.setattr(settings, "CHUNK_OVERLAP", 20)
    engine, _ = make_engine(tmp_path)
    text = "# Parent\n## Leaf\n\n" + "alpha fact; " * 20 + "\n\n```python\n# code heading\nanswer = 42\n```\n"
    chunks = engine._chunk_text(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert all("# Parent\n## Leaf" in chunk for chunk in chunks)
    combined = "\n".join(chunks)
    assert "alpha fact" in combined
    assert "# code heading" in combined
    assert "answer = 42" in combined
    assert not any(chunk.strip() in {"# Parent", "## Leaf", "---"} for chunk in chunks)


def test_heading_breadcrumbs_follow_normal_section_blocks_and_siblings(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHUNK_SIZE", 96)
    engine, _ = make_engine(tmp_path)
    text = "# Parent\nparent intro\n## Leaf\n" + ("leaf fact; " * 12) + "\n## Sibling\nsibling fact"
    chunks = engine._chunk_text(text)
    leaf_chunks = [chunk for chunk in chunks if "leaf fact" in chunk]
    sibling_chunks = [chunk for chunk in chunks if "sibling fact" in chunk]

    assert leaf_chunks and sibling_chunks
    assert all("# Parent\n## Leaf" in chunk for chunk in leaf_chunks)
    assert all("# Parent\n## Sibling" in chunk for chunk in sibling_chunks)
    assert all("## Leaf" not in chunk for chunk in sibling_chunks)


def test_long_heading_path_preserves_body_within_chunk_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CHUNK_SIZE", 80)
    engine, _ = make_engine(tmp_path)
    text = "# " + "Parent title " * 8 + "\n## " + "Leaf title " * 8 + "\ncritical body fact"
    chunks = engine._chunk_text(text)
    assert chunks
    assert all(len(chunk) <= 80 for chunk in chunks)
    assert any("critical body fact" in chunk for chunk in chunks)
    assert all(not engine._is_structural_only(chunk) for chunk in chunks)


def test_search_normalizes_vectors_and_filters_by_cosine_similarity(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RAG_MIN_SIMILARITY", 0.8, raising=False)
    engine, _ = make_engine(tmp_path)
    async def varied_embedding(text):
        return [1.0, 0.0] if text == "question" else [0.0, 1.0]
    engine._get_embedding = varied_embedding
    engine.metadata = [{"text": "orthogonal", "source": "test"}]
    engine.index = __import__("faiss").IndexFlatL2(2)
    engine.index.add(__import__("numpy").array([[0.0, 1.0]], dtype="float32"))
    assert asyncio.run(engine.search("question")) == []
    assert asyncio.run(engine.search("question", top_k=0)) == []


def test_search_handles_zero_or_nonfinite_query_vectors(tmp_path):
    engine, _ = make_engine(tmp_path)
    engine.metadata = [{"text": "content"}]
    engine.index = __import__("faiss").IndexFlatL2(2)
    engine.index.add(__import__("numpy").array([[1.0, 0.0]], dtype="float32"))
    async def invalid(_text):
        return [0.0, 0.0]
    engine._get_embedding = invalid
    assert asyncio.run(engine.search("question")) == []


def test_rebuild_stores_unit_length_vectors(tmp_path):
    engine, _ = make_engine(tmp_path)
    async def scaled_embedding(_text):
        return [3.0, 4.0]
    engine._get_embedding = scaled_embedding
    asyncio.run(engine.rebuild_index())
    stored = engine.index.reconstruct(0)
    assert sum(float(value) ** 2 for value in stored) == pytest.approx(1.0)


def test_load_legacy_index_normalizes_vectors_in_memory(tmp_path):
    import faiss
    import numpy as np
    import json

    index_dir = tmp_path / "legacy"
    index_dir.mkdir()
    legacy = faiss.IndexFlatL2(2)
    legacy.add(np.asarray([[3.0, 4.0]], dtype="float32"))
    faiss.write_index(legacy, str(index_dir / "index.faiss"))
    (index_dir / "metadata.json").write_text(json.dumps([{"text": "legacy"}]), encoding="utf-8")
    engine = RAGEngine(str(tmp_path / "knowledge.md"), str(index_dir))
    stored = engine.index.reconstruct(0)
    assert sum(float(value) ** 2 for value in stored) == pytest.approx(1.0)


def test_search_empty_index_returns_empty(tmp_path):
    import faiss

    engine, _ = make_engine(tmp_path)
    engine.index = faiss.IndexFlatL2(2)
    engine.metadata = []
    assert asyncio.run(engine.search("question")) == []
