from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


user_roles = Table("user_roles", Base.metadata, Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True), Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True))
role_permissions = Table("role_permissions", Base.metadata, Column("role_id", ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True), Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True))


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
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    max_devices: Mapped[int] = mapped_column(Integer, default=1)
    price_minor: Mapped[int] = mapped_column(Integer, default=0)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Subscription(Base):
    __tablename__ = "subscriptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    node_keys: Mapped[list] = mapped_column(JSON, default=list)
    config_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    used_gb: Mapped[float] = mapped_column(Float, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    key_prefix: Mapped[str] = mapped_column(String(16), index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(80), default="")
    resource_id: Mapped[str] = mapped_column(String(80), default="")
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    value_enc: Mapped[str] = mapped_column(Text)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SystemState(Base):
    __tablename__ = "system_state"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    mode: Mapped[str] = mapped_column(String(24), default="NORMAL")
    international_failures: Mapped[int] = mapped_column(Integer, default=0)
    international_successes: Mapped[int] = mapped_column(Integer, default=0)
    ai_status: Mapped[str] = mapped_column(String(24), default="DISABLED")
    optimizer_status: Mapped[str] = mapped_column(String(24), default="IDLE")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ResearchFinding(Base):
    __tablename__ = "research_findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    __table_args__ = (UniqueConstraint("source", "version", name="uq_research_source_version"),)
