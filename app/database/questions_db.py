import pickle
import numpy as np
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
from app.database.models import Base, UniqueQuestion
from app.config import settings
from openai import OpenAI
from loguru import logger

DATABASE_URL = "sqlite+aiosqlite:///./data/database.db"

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

class QuestionsDB:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    async def init_db(self):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    def _get_embedding(self, text: str) -> np.ndarray:
        response = self.client.embeddings.create(
            input=text,
            model="text-embedding-3-small"
        )
        return np.array(response.data[0].embedding)

    def _cosine_similarity(self, v1, v2):
        return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

    async def add_question(self, question: str, source: str) -> bool:
        """Добавление вопроса с проверкой на уникальность."""
        new_emb = self._get_embedding(question)
        
        async with async_session() as session:
            result = await session.execute(select(UniqueQuestion))
            questions = result.scalars().all()
            
            for q in questions:
                existing_emb = pickle.loads(q.embedding)
                similarity = self._cosine_similarity(new_emb, existing_emb)
                
                if similarity >= settings.SIMILARITY_THRESHOLD:
                    # Не уникальный, инкрементируем счетчик
                    q.count += 1
                    await session.commit()
                    return False
            
            # Уникальный, сохраняем
            new_q = UniqueQuestion(
                question=question,
                embedding=pickle.dumps(new_emb),
                source=source
            )
            session.add(new_q)
            await session.commit()
            return True

    async def get_all_questions(self):
        async with async_session() as session:
            result = await session.execute(select(UniqueQuestion).order_by(UniqueQuestion.created_at.desc()))
            return result.scalars().all()
