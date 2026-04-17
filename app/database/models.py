"""ORM-модели для БД вопросов.

Используется SQLAlchemy для хранения уникальных вопросов и связанных
embeddings в бинарном виде (pickle).
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, LargeBinary
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class UniqueQuestion(Base):
    """Сущность уникального вопроса.

    `embedding` хранится как pickle-байты, чтобы избежать отдельной
    векторной БД на данном этапе.
    """
    __tablename__ = "unique_questions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(String, nullable=False)
    embedding = Column(LargeBinary, nullable=False)  # Pickle or binary
    source = Column(String, nullable=False)  # "telegram" or "jivo"
    created_at = Column(DateTime, default=datetime.utcnow)
    count = Column(Integer, default=1)
