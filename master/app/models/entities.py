from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(254), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    roles: Mapped[list["Role"]] = relationship(secondary=user_roles, back_populates="users", lazy="selectin")

    @property
    def role(self) -> str:
        priority = {"SUPER_ADMIN": 0, "ADMIN": 1, "OPERATOR": 2, "RESELLER": 3, "USER": 4}
        return min((r.name for r in self.roles), key=lambda x: priority.get(x, 99), default="USER")


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    users: Mapped[list[User]] = relationship(secondary=user_roles, back_populates="roles")
    permissions: Mapped[list["Permission"]] = relationship(secondary=role_permissions, back_populates="roles", lazy="selectin")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    roles: Mapped[list[Role]] = relationship(secondary=role_permissions, back_populates="permissions")


class Node(Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    node_key: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    endpoint: Mapped[str] = mapped_column(String(255))
    agent_token_hash: Mapped[str] = mapped_column(String(128), unique=True)
    agent_token_enc: Mapped[str] = mapped_column(Text)
    ssh_config_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_version: Mapped[str] = mapped_column(String(64), default="unknown")
    status: Mapped[str] = mapped_column(String(24), default="UNKNOWN", index=True)
    score: Mapped[float] = mapped_column(Float, default=0)
    cpu_percent: Mapped[float] = mapped_column(Float, default=0)
    memory_percent: Mapped[float] = mapped_column(Float, default=0)
    traffic_rx_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    traffic_tx_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    core: Mapped[str] = mapped_column(String(32), default="unknown")
    core_version: Mapped[str] = mapped_column(String(64), default="")
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Route(Base):
    __tablename__ = "routes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    node_keys: Mapped[list] = mapped_column(JSON, default=list)
    core: Mapped[str] = mapped_column(String(32), default="xray")
    protocol: Mapped[str] = mapped_column(String(64), default="vless")
    transport: Mapped[str] = mapped_column(String(64), default="tcp")
    config_enc: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(24), default="CANDIDATE", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_golden: Mapped[bool] = mapped_column(Boolean, default=False)
    consecutive_wins: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[str] = mapped_column(String(80), index=True)
    route_hash: Mapped[str] = mapped_column(String(128), index=True)
    config_hash: Mapped[str] = mapped_column(String(128), index=True)
    node_keys: Mapped[list] = mapped_column(JSON, default=list)
    core: Mapped[str] = mapped_column(String(32))
    protocol: Mapped[str] = mapped_column(String(64))
    transport: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    jitter_ms: Mapped[float] = mapped_column(Float, default=0)
    packet_loss_percent: Mapped[float] = mapped_column(Float, default=0)
    throughput_mbps: Mapped[float] = mapped_column(Float, default=0)
    stability_percent: Mapped[float] = mapped_column(Float, default=0)
    level: Mapped[str] = mapped_column(String(24), default="EXPERIMENTAL", index=True)
    decision: Mapped[str] = mapped_column(String(24), default="KEEP")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Decision(Base):
    __tablename__ = "optimizer_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    current_score: Mapped[float] = mapped_column(Float)
    proposed_score: Mapped[float] = mapped_column(Float)
    action: Mapped[str] = mapped_column(String(24))
    candidate_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    ai_called: Mapped[bool] = mapped_column(Boolean, default=False)
    model: Mapped[str] = mapped_column(String(64), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cached_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class Metric(Base):
    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    latency_ms: Mapped[float] = mapped_column(Float, default=0)
    jitter_ms: Mapped[float] = mapped_column(Float, default=0)
    packet_loss_percent: Mapped[float] = mapped_column(Float, default=0)
    throughput_mbps: Mapped[float] = mapped_column(Float, default=0)
    cpu_percent: Mapped[float] = mapped_column(Float, default=0)
    memory_percent: Mapped[float] = mapped_column(Float, default=0)
    stability_percent: Mapped[float] = mapped_column(Float, default=0)
    measured_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (Index("ix_metrics_node_measured_at", "node_id", "measured_at"),)


class Traffic(Base):
    __tablename__ = "traffic"

    id: Mapped[int] = mapped_column(primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"), index=True)
    rx_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    tx_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    sampled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (Index("ix_traffic_node_sampled_at", "node_id", "sampled_at"),)


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    quota_gb: Mapped[float] = mapped_column(Float, default=0)
