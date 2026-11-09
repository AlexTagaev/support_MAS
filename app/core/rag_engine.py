"""RAG-движок: индексирование Markdown базы знаний и поиск по FAISS.

Модуль отвечает за:
- разбиение базы знаний в формате Markdown на чанки;
- получение embeddings через OpenAI-совместимый API;
- построение/загрузку FAISS индекса и выдачу релевантных фрагментов.
"""

import json
import os
import asyncio
import threading
import tempfile
import uuid
from functools import lru_cache
from pathlib import Path
import faiss
import numpy as np
from typing import Dict
from typing import List
from loguru import logger

from app.config import settings
from app.core.provider_clients import get_async_client


@lru_cache(maxsize=1)
def get_rag_engine():
    """Return the shared in-process RAG instance used by all application paths."""
    return RAGEngine(settings.KNOWLEDGE_BASE_PATH, settings.FAISS_INDEX_PATH)

class RAGEngine:
    """Индексатор и поисковик по базе знаний для RAG.

    Хранение:
    - FAISS индекс: `index.faiss`
    - метаданные чанков: `metadata.json`

    Примечание: индекс пересоздаётся из Markdown-файла базы знаний и
    используется для семантического поиска фрагментов, которые затем
    подаются в LLM как контекст.
    """
    def __init__(self, knowledge_base_path: str, index_path: str):
        """Создаёт объект RAGEngine и загружает индекс при наличии."""
        self.kb_path = knowledge_base_path
        self.index_path = index_path
        self.index = None
        self.metadata = []
        self._lock = threading.RLock()
        self._rebuild_lock = asyncio.Lock()
        
        try:
            self.load_index()
        except Exception as exc:
            # Keep the API/admin available so the index can be rebuilt from the
            # admin panel. Readiness reports the missing index until then.
            logger.warning("FAISS index unavailable; rebuild is required: {}", exc)

    async def _get_embedding(self, text: str) -> List[float]:
        """Возвращает embedding для текста через OpenAI embeddings API."""
        client = get_async_client()
        response = await client.embeddings.create(input=text, model="text-embedding-3-small")
        return response.data[0].embedding

    @staticmethod
    def _is_md_heading(line: str) -> bool:
        """Проверяет, что строка является Markdown-заголовком."""
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            return False
        after_hashes = stripped.lstrip("#")
        return after_hashes.startswith(" ")

    @staticmethod
    def _is_md_rule(line: str) -> bool:
        """Проверяет, что строка является Markdown-разделителем."""
        stripped = line.strip()
        return stripped in {"---", "***", "___"}

    def _split_md_to_blocks(self, text: str) -> List[str]:
        """Разбивает Markdown на логические блоки.

        Приоритет: заголовки и горизонтальные разделители. Внутри fenced
        блоков кода (```), разбиение по заголовкам не применяется.
        """
        blocks: List[str] = []
        current: List[str] = []
        in_code_block = False

        for raw_line in text.splitlines():
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                current.append(line)
                continue

            if not in_code_block and (self._is_md_heading(line) or
                                      self._is_md_rule(line)):
                if current:
                    block = "\n".join(current).strip()
                    if block:
                        blocks.append(block)
                    current = []

                current.append(line)
                continue

            current.append(line)

        if current:
            block = "\n".join(current).strip()
            if block:
                blocks.append(block)

        return blocks

    def _split_md_block_by_paragraphs(self, text: str) -> List[str]:
        """Делит Markdown-блок на сегменты по пустым строкам.

        Внутри fenced блоков кода (```), пустые строки не считаются
        разделителями.
        """
        segments: List[str] = []
        current: List[str] = []
        in_code_block = False

        for raw_line in text.splitlines():
            line = raw_line.rstrip("\n")
            stripped = line.strip()

            if stripped.startswith("```"):
                in_code_block = not in_code_block
                current.append(line)
                continue

            if not in_code_block and stripped == "":
                seg = "\n".join(current).strip()
                if seg:
                    segments.append(seg)
                current = []
                continue

            current.append(line)

        seg = "\n".join(current).strip()
        if seg:
            segments.append(seg)

        return segments

    def _hard_split_with_overlap(self, text: str) -> List[str]:
        """Резервное разбиение по символам, если сегмент слишком большой.

        Используется только как последний шаг, чтобы гарантировать, что
        чанк не превышает `settings.CHUNK_SIZE`.
        """
        max_size = max(1, int(settings.CHUNK_SIZE))
        overlap = max(0, int(settings.CHUNK_OVERLAP))
        if overlap >= max_size:
            overlap = max(0, max_size // 4)

        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + max_size)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = max(0, end - overlap)

        return chunks

    def _pack_segments_to_chunks(self, segments: List[str]) -> List[str]:
        """Собирает сегменты в чанки, соблюдая `CHUNK_SIZE` и overlap."""
        max_size = max(1, int(settings.CHUNK_SIZE))
        overlap = max(0, int(settings.CHUNK_OVERLAP))
        if overlap >= max_size:
            overlap = max(0, max_size // 4)

        chunks: List[str] = []
        current = ""

        for segment in segments:
            if not segment:
                continue

            if len(segment) > max_size:
                if current.strip():
                    chunks.append(current.strip())
                    current = ""
                chunks.extend(self._hard_split_with_overlap(segment))
                continue

            candidate = segment if not current else f"{current}\n\n{segment}"
            if len(candidate) <= max_size:
                current = candidate
                continue

            if current.strip():
                chunks.append(current.strip())

            prefix = ""
            if chunks and overlap > 0:
                prefix = chunks[-1][-overlap:].strip()

            current = segment
            if prefix:
                candidate = f"{prefix}\n\n{segment}"
                if len(candidate) <= max_size:
                    current = candidate

        if current.strip():
            chunks.append(current.strip())

        return chunks

    def _chunk_text(self, text: str) -> List[str]:
        """Разбивка Markdown-текста на чанки для RAG.

        Логика:
        - сначала разбиение по структуре Markdown (заголовки/разделители),
        - затем при необходимости ужатие блоков до `settings.CHUNK_SIZE`,
          стараясь не ломать fenced блоки кода.

        `settings.CHUNK_SIZE` остаётся верхним лимитом: он нужен как защита
        от слишком длинных фрагментов (embeddings API и качество поиска).
        """
        if not text.strip():
            return []

        blocks = self._split_md_to_blocks(text)
        chunks: List[str] = []

        for block in blocks:
            if len(block) <= settings.CHUNK_SIZE:
                chunks.append(block.strip())
                continue

            segments = self._split_md_block_by_paragraphs(block)
            chunks.extend(self._pack_segments_to_chunks(segments))

        return [c for c in chunks if c.strip() and not self._is_structural_only(c)]

    @classmethod
    def _is_structural_only(cls, text: str) -> bool:
        """Exclude standalone Markdown headings and separators from retrieval."""
        meaningful = [line.strip() for line in text.splitlines() if line.strip()]
        return not meaningful or all(
            cls._is_md_rule(line) or (line.startswith("#") and cls._is_md_heading(line))
            for line in meaningful
        )

    async def rebuild_index(self) -> None:
        """Serialize concurrent rebuilds so disk and memory publish the same generation."""
        async with self._rebuild_lock:
            await self._build_and_publish_index()

    async def _build_and_publish_index(self) -> None:
        """Пересоздаёт FAISS индекс из Markdown-файла базы знаний."""
        logger.info(f"Rebuilding index from {self.kb_path}")
        if not os.path.exists(self.kb_path):
            raise FileNotFoundError(f"Knowledge base file not found: {self.kb_path}")

        with open(self.kb_path, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = self._chunk_text(content)
        embeddings = []
        metadata = []

        for i, chunk in enumerate(chunks):
            emb = await self._get_embedding(chunk)
            embeddings.append(emb)
            metadata.append({
                "chunk_id": f"kb_{i:03d}",
                "text": chunk,
                "source": "knowledge_base.md"
            })

        if not chunks:
            raise ValueError("Knowledge base is empty; cannot build the search index.")
        embeddings_np = np.array(embeddings, dtype="float32")
        if embeddings_np.ndim != 2 or embeddings_np.shape[0] != len(metadata):
            raise ValueError("Embedding response count does not match knowledge chunks.")
        dimension = embeddings_np.shape[1]

        candidate_index = faiss.IndexFlatL2(dimension)
        candidate_index.add(embeddings_np)
        if candidate_index.ntotal != len(metadata):
            raise ValueError("FAISS vector count does not match metadata count.")

        # Publish index and metadata as one generation, then atomically switch CURRENT.
        base = Path(self.index_path)
        generations = base / "generations"
        generations.mkdir(parents=True, exist_ok=True)
        generation = uuid.uuid4().hex
        temp_dir = Path(tempfile.mkdtemp(prefix=".building-", dir=generations))
        final_dir = generations / generation
        try:
            faiss.write_index(candidate_index, str(temp_dir / "index.faiss"))
            with (temp_dir / "metadata.json").open("w", encoding="utf-8") as f:
                json.dump(metadata, f, ensure_ascii=False, indent=2)
            # Validate what will be read after a restart before publishing it.
            loaded_index = faiss.read_index(str(temp_dir / "index.faiss"))
            with (temp_dir / "metadata.json").open("r", encoding="utf-8") as f:
                loaded_metadata = json.load(f)
            if loaded_index.ntotal != len(loaded_metadata) or len(loaded_metadata) != len(chunks):
                raise ValueError("Staged FAISS generation failed validation.")
            os.replace(temp_dir, final_dir)
            pointer_tmp = base / f".CURRENT-{generation}"
            pointer_tmp.write_text(generation, encoding="ascii")
            os.replace(pointer_tmp, base / "CURRENT")
        except Exception:
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise

        with self._lock:
            self.index = candidate_index
            self.metadata = metadata
        
        logger.info("Index rebuilt successfully.")

    def load_index(self) -> None:
        """Загрузка индекса с диска."""
        base = Path(self.index_path)
        pointer = base / "CURRENT"
        if pointer.exists():
            generation = pointer.read_text(encoding="ascii").strip()
            if not generation or Path(generation).name != generation:
                raise ValueError("Invalid FAISS generation pointer.")
            generation_dir = base / "generations" / generation
        else:
            # Read legacy index layout for existing installations.
            generation_dir = base
        loaded_index = faiss.read_index(str(generation_dir / "index.faiss"))
        with (generation_dir / "metadata.json").open("r", encoding="utf-8") as f:
            loaded_metadata = json.load(f)
        if loaded_index.ntotal != len(loaded_metadata):
            raise ValueError("FAISS index vector count does not match metadata.")
        with self._lock:
            self.index = loaded_index
            self.metadata = loaded_metadata
        logger.info("Index loaded from disk.")

    async def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """Семантический поиск релевантных фрагментов."""
        if not query.strip():
            return []

        # Don't spend an embeddings request when the application has not yet
        # built an index. Keep a consistent index/metadata snapshot across the
        # async API call and FAISS lookup.
        with self._lock:
            index = self.index
            metadata = self.metadata
        if index is None:
            return []

        query_emb = np.array([await self._get_embedding(query)]).astype('float32')
        distances, indices = index.search(query_emb, top_k)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx < len(metadata):
                # Ограничение текущей реализации: в IndexFlatL2 меньше = лучше.
                # Если понадобится cosine similarity, нужно перейти на IndexFlatIP
                # и нормализовать эмбеддинги.
                results.append({
                    "text": metadata[idx]["text"],
                    "score": float(distances[0][i]),
                    "metadata": metadata[idx]
                })
        return results

    async def get_context_for_query(self, query: str) -> str:
        """Формирование контекста для GPT."""
        results = await self.search(query, top_k=settings.TOP_K_RESULTS)
        context_parts = [r["text"] for r in results]
        return "\n\n---\n\n".join(context_parts)
