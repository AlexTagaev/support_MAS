"""RAG-движок: индексирование Markdown базы знаний и поиск по FAISS.

Модуль отвечает за:
- разбиение базы знаний в формате Markdown на чанки;
- получение embeddings через OpenAI-совместимый API;
- построение/загрузку FAISS индекса и выдачу релевантных фрагментов.
"""

import json
import os
import faiss
import numpy as np
from typing import Dict
from typing import List
from openai import OpenAI
from loguru import logger

from app.config import settings

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
        
        if os.path.exists(os.path.join(self.index_path, "index.faiss")):
            self.load_index()
        else:
            logger.warning("FAISS index not found. Please rebuild index.")

    @staticmethod
    def _build_client() -> OpenAI:
        """Создаёт embeddings-клиента по текущему провайдеру."""
        if settings.LLM_PROVIDER == "proxiapi":
            return OpenAI(
                api_key=settings.PROXIAPI_API_KEY,
                base_url=settings.PROXIAPI_API_BASE
            )
        return OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )

    def _get_embedding(self, text: str) -> List[float]:
        """Возвращает embedding для текста через OpenAI embeddings API."""
        response = self._build_client().embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
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

            if prefix:
                current = f"{prefix}\n\n{segment}"
            else:
                current = segment

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

        return [c for c in chunks if c.strip()]

    def rebuild_index(self) -> None:
        """Пересоздаёт FAISS индекс из Markdown-файла базы знаний."""
        logger.info(f"Rebuilding index from {self.kb_path}")
        if not os.path.exists(self.kb_path):
            logger.error(f"Knowledge base file not found: {self.kb_path}")
            return

        with open(self.kb_path, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = self._chunk_text(content)
        embeddings = []
        self.metadata = []

        for i, chunk in enumerate(chunks):
            emb = self._get_embedding(chunk)
            embeddings.append(emb)
            self.metadata.append({
                "chunk_id": f"kb_{i:03d}",
                "text": chunk,
                "source": "knowledge_base.md"
            })

        embeddings_np = np.array(embeddings).astype('float32')
        dimension = embeddings_np.shape[1]
        
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(embeddings_np)

        # Важно: сохраняем индекс и метаданные атомарно в одну директорию,
        # чтобы при рестарте сервиса можно было быстро восстановиться.
        if not os.path.exists(self.index_path):
            os.makedirs(self.index_path)
        
        faiss.write_index(self.index, os.path.join(self.index_path, "index.faiss"))
        with open(os.path.join(self.index_path, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=4)
        
        logger.info("Index rebuilt successfully.")

    def load_index(self) -> None:
        """Загрузка индекса с диска."""
        self.index = faiss.read_index(os.path.join(self.index_path, "index.faiss"))
        with open(os.path.join(self.index_path, "metadata.json"), "r", encoding="utf-8") as f:
            self.metadata = json.load(f)
        logger.info("Index loaded from disk.")

    async def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """Семантический поиск релевантных фрагментов."""
        if self.index is None:
            return []

        query_emb = np.array([self._get_embedding(query)]).astype('float32')
        distances, indices = self.index.search(query_emb, top_k)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx != -1 and idx < len(self.metadata):
                # Ограничение текущей реализации: в IndexFlatL2 меньше = лучше.
                # Если понадобится cosine similarity, нужно перейти на IndexFlatIP
                # и нормализовать эмбеддинги.
                results.append({
                    "text": self.metadata[idx]["text"],
                    "score": float(distances[0][i]),
                    "metadata": self.metadata[idx]
                })
        return results

    async def get_context_for_query(self, query: str) -> str:
        """Формирование контекста для GPT."""
        results = await self.search(query, top_k=settings.TOP_K_RESULTS)
        context_parts = [r["text"] for r in results]
        return "\n\n---\n\n".join(context_parts)
