import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class VoiceUpdate(Base):
    __tablename__ = "voice_updates"
    __table_args__ = (Index("ix_voice_updates_user_id_created_at", "user_id", "created_at"),)
    # Return server defaults (created_at) from the INSERT itself, no extra SELECT.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # When the user spoke, as sent by the client.
    client_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # When the server stored it.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # User's IANA timezone at the time of the update.
    timezone: Mapped[str] = mapped_column(String(64))
    transcript: Mapped[str] = mapped_column(Text)
    is_eating_update: Mapped[bool] = mapped_column(Boolean)
