import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text

try:
    from backend.app.core.database import Base
except ImportError:
    from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    sender_id = Column(String(36), nullable=False, index=True)
    receiver_id = Column(String(36), nullable=False, index=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False)
