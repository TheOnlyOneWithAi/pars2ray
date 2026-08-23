from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClientRuntime(Base):
    __tablename__ = "client_runtime"
    id: Mapped[int] = mapped_column(primary_key=True)
    subscription_id: Mapped[int] = mapped_column(ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True)
    ip_limit: Mapped[int] = mapped_column(Integer, default=0)
    online_ips: Mapped[list] = mapped_column(JSON, default=list)
    last_online_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    __table_args__ = (UniqueConstraint("subscription_id", name="uq_client_runtime_subscription"), Index("ix_client_runtime_last_online", "last_online_at"))
