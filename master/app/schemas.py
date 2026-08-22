from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=12, max_length=256)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=32)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str | None = Field(default=None, max_length=254)
    password: str | None = Field(default=None, min_length=12, max_length=256)
    role: Literal["SUPER_ADMIN", "ADMIN", "OPERATOR", "RESELLER", "USER"] = "USER"
    is_active: bool = True
    plan_id: int | None = Field(default=None, ge=1)
    node_keys: list[str] = Field(default_factory=list, max_length=20)
    inbound_ids: list[int] = Field(default_factory=list, max_length=32)
    quota_gb: float = Field(default=0, ge=0)
    duration_days: int = Field(default=0, ge=0, le=36500)
    expires_at: datetime | None = None


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=254)
    role: Literal["SUPER_ADMIN", "ADMIN", "OPERATOR", "RESELLER", "USER"] | None = None
    is_active: bool | None = None
    quota_gb: float | None = Field(default=None, ge=0)
    duration_days: int | None = Field(default=None, ge=0, le=36500)
    expires_at: datetime | None = None


class UserOut(ORMModel):
    id: int
    username: str
    email: str | None
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None
    plan_id: int | None = None
    quota_gb: float | None = None
    used_gb: float | None = None
    expires_at: datetime | None = None
    subscription_token: str | None = None


class NodeRegisterRequest(BaseModel):
    node_key: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z]{2}\d{0,3}$")
    country: str = Field(min_length=2, max_length=2)
    endpoint: str = Field(min_length=8, max_length=255)
    agent_token: str = Field(min_length=32, max_length=256)
    agent_version: str = Field(default="unknown", max_length=64)

    @field_validator("country")
    @classmethod
    def uppercase_country(cls, value: str) -> str:
        return value.upper()

    @field_validator("endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("endpoint must use http or https")
        return value.rstrip("/")


class NodeOut(ORMModel):
    id: int
    node_key: str
    country: str
    endpoint: str
    status: str
    score: float
    cpu_percent: float
    memory_percent: float
    traffic_rx_bytes: int
    traffic_tx_bytes: int
    core: str
    core_version: str
    capabilities: dict[str, Any]
    last_seen_at: datetime | None
    created_at: datetime


class BenchmarkRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=443, ge=1, le=65535)
    attempts: int = Field(default=5, ge=1, le=20)
    timeout_seconds: float = Field(default=3.0, ge=0.2, le=15.0)


class RouteCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    node_keys: list[str] = Field(min_length=1, max_length=20)
    core: Literal["xray", "sing-box"] = "xray"
    protocol: Literal["vless", "vmess", "trojan", "shadowsocks", "hysteria2"] = "vless"
    transport: Literal["tcp", "grpc", "websocket", "httpupgrade", "xhttp", "quic"] = "tcp"
    config: dict[str, Any] = Field(default_factory=dict)


class ConfigBuildRequest(BaseModel):
    clients: list[dict[str, str]] = Field(default_factory=list, max_length=10000)
    apply: bool = False


class RouteOut(ORMModel):
    id: int
    name: str
    node_keys: list[str]
    core: str
    protocol: str
    transport: str
    status: str
    score: float
    is_active: bool
    is_golden: bool
    consecutive_wins: int
    updated_at: datetime


class ExperimentOut(ORMModel):
    id: int
    candidate_id: str
    node_keys: list[str]
    core: str
    protocol: str
    transport: str
    score: float
    latency_ms: float
    jitter_ms: float
    packet_loss_percent: float
    throughput_mbps: float
    stability_percent: float
    level: str
    decision: str
    created_at: datetime


class DecisionOut(ORMModel):
    id: int
    current_score: float
    proposed_score: float
    action: str
    candidate_id: str | None
    reason: str
    ai_called: bool
    model: str
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    created_at: datetime


class MetricOut(ORMModel):
    id: int
    latency_ms: float
    jitter_ms: float
    packet_loss_percent: float
    throughput_mbps: float
    cpu_percent: float
    memory_percent: float
    stability_percent: float
    measured_at: datetime


class PlanOut(ORMModel):
    id: int
    name: str
    quota_gb: float
    duration_days: int
    max_devices: int
    price_minor: int
    enabled: bool


class SubscriptionOut(ORMModel):
    id: int
    user_id: int
    plan_id: int | None
    node_keys: list[str]
    enabled: bool
    used_gb: float
    expires_at: datetime | None
    created_at: datetime


class ClientCreate(BaseModel):
    user_id: int = Field(gt=0)
    plan_id: int | None = Field(default=None, ge=1)
    node_keys: list[str] = Field(default_factory=list, max_length=20)
    quota_gb: float | None = Field(default=None, ge=0)
    duration_days: int | None = Field(default=None, ge=0, le=36500)
    expires_at: datetime | None = None
    single_active: bool = True


class ClientUpdate(BaseModel):
    plan_id: int | None = Field(default=None, ge=1)
    clear_plan: bool = False
    node_keys: list[str] | None = Field(default=None, max_length=20)
    quota_gb: float | None = Field(default=None, ge=0)
    duration_days: int | None = Field(default=None, ge=0, le=36500)
    enabled: bool | None = None
    expires_at: datetime | None = None


class ClientOut(BaseModel):
    id: int
    user_id: int
    username: str
    plan_id: int | None
    plan_name: str | None
    client_id: str
    node_keys: list[str]
    enabled: bool
    used_gb: float
    quota_gb: float
    expires_at: datetime | None
    created_at: datetime


class AuditLogOut(ORMModel):
    id: int
    actor_user_id: int | None
    action: str
    resource_type: str
    resource_id: str
    ip_address: str
    created_at: datetime


class ResearchFindingOut(ORMModel):
    id: int
    source: str
    version: str
    title: str
    notes: str
    url: str
    created_at: datetime


class ExperimentCreate(BaseModel):
    candidate_id: str = Field(min_length=1, max_length=80)
    route_hash: str = Field(min_length=8, max_length=128)
    config_hash: str = Field(min_length=8, max_length=128)
    node_keys: list[str] = Field(min_length=1, max_length=20)
    core: str = Field(max_length=32)
    protocol: str = Field(max_length=64)
    transport: str = Field(max_length=64)
    score: float = Field(ge=0, le=100)
    latency_ms: float = Field(default=0, ge=0)
    jitter_ms: float = Field(default=0, ge=0)
    packet_loss_percent: float = Field(default=0, ge=0, le=100)
    throughput_mbps: float = Field(default=0, ge=0)
    stability_percent: float = Field(default=0, ge=0, le=100)
    level: Literal["GOLDEN", "VERIFIED", "EXPERIMENTAL"] = "EXPERIMENTAL"
    decision: str = Field(default="KEEP", max_length=24)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OptimizerRequest(BaseModel):
    current_score: float = Field(ge=0, le=100)
    previous_score: float | None = Field(default=None, ge=0, le=100)
    anomaly: bool = False
    new_method: bool = False
    route_failed: bool = False
    optimization_requested: bool = False
    current_route: dict[str, Any] = Field(default_factory=dict)
    candidates: list[dict[str, Any]] = Field(default_factory=list, max_length=50)


class SystemSettingUpdate(BaseModel):
    value: str = Field(max_length=100000)


class PanelDomainUpdate(BaseModel):
    domain: str = Field(min_length=4, max_length=253)
    tls: bool = True
    email: str | None = Field(default=None, max_length=254)


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    scopes: list[Literal["read", "write", "admin", "*"]] = Field(default_factory=list, max_length=20)
    expires_in_days: int | None = Field(default=None, ge=1, le=3650)


class ApiKeyOut(ORMModel):
    id: int
    name: str
    key_prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    expires_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class PlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    quota_gb: float = Field(ge=0)
    duration_days: int = Field(ge=0, le=3650)
    max_devices: int = Field(ge=1, le=100)
    price_minor: int = Field(ge=0)


class SubscriptionCreate(BaseModel):
    user_id: int = Field(gt=0)
    plan_id: int | None = Field(default=None, gt=0)
    node_keys: list[str] = Field(default_factory=list, max_length=20)
    expires_at: datetime | None = None
