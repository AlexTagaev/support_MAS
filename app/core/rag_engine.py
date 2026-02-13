import os
import faiss
import numpy as np
from typing import List, Dict
from openai import OpenAI
from app.config import settings
from loguru import logger

class RAGEngine:
    def __init__(self, knowledge_base_path: str, index_path: str):
        self.kb_path = knowledge_base_path
        self.index_path = index_path
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.index = None
        self.metadata = []
        
        if os.path.exists(os.path.join(self.index_path, "index.faiss")):
            self.load_index()
        else:
            logger.warning("FAISS index not found. Please rebuild index.")

    def _get_embedding(self, text: str) -> List[float]:
        """Получение embedding через OpenAI API."""
        response = self.client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return response.data[0].embedding

    def _chunk_text(self, text: str) -> List[str]:
        """Разбивка текста на чанки."""
        # Простая реализация чанкинга (можно улучшить по ТЗ)
        chunks = []
        lines = text.split("\n")
        current_chunk = ""
        
        for line in lines:
            if len(current_chunk) + len(line) < settings.CHUNK_SIZE:
                current_chunk += line + "\n"
            else:
                chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
        if current_chunk:
            chunks.append(current_chunk.strip())
        return chunks

    def rebuild_index(self) -> None:
        """Пересоздание индекса из .md файла."""
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

        # Сохранение
        if not os.path.exists(self.index_path):
            os.makedirs(self.index_path)
        
        faiss.write_index(self.index, os.path.join(self.index_path, "index.faiss"))
        import json
        with open(os.path.join(self.index_path, "metadata.json"), "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=4)
        
        logger.info("Index rebuilt successfully.")

    def load_index(self) -> None:
        """Загрузка индекса с диска."""
        self.index = faiss.read_index(os.path.join(self.index_path, "index.faiss"))
        import json
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
                # В FAISS IndexFlatL2 distance - это L2 расстояние. 
                # Для cosine similarity нужно использовать IndexFlatIP с нормализацией.
                # Здесь используем упрощенный score.
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
