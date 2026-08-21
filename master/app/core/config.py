from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_DEV_JWT = "dev-only-change-jwt-secret-please-rotate"
_DEV_MASTER = "dev-only-change-master-secret-please-rotate"
_DEV_ADMIN = "dev-admin-password-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    app_name: str = "Pars2Ray Enterprise"
    app_version: str = "2.2.0"
    environment: str = "production"
    debug: bool = False
    # Native v2 intentionally defaults to SQLite so a fresh installation needs
    # no PostgreSQL/Redis/Docker services. PostgreSQL remains supported when a
    # deployment explicitly supplies a PostgreSQL DATABASE_URL.
    database_url: str = "sqlite:////opt/pars2ray/data/pars2ray.db"
    redis_url: str = ""
    jwt_secret: str = Field(default=_DEV_JWT, min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    master_secret: str = Field(default=_DEV_MASTER, min_length=32)
    admin_user: str = "admin"
    admin_password: str = Field(default=_DEV_ADMIN, min_length=12)
    admin_email: str = "admin@example.invalid"
    cors_origins: str = ""
    trusted_hosts: str = "localhost,127.0.0.1"
    rate_limit_per_minute: int = 120
    node_poll_seconds: int = 30
    worker_poll_seconds: int = 10
    agent_request_timeout_seconds: int = 10
    openai_api_key: str = ""
    openai_model: str = "gpt-5-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_request_timeout_seconds: float = 15.0
    ai_enabled: bool = False
    ai_min_score_change: float = 5.0
    ai_switch_min_improvement: float = 10.0
    ai_required_wins: int = 3
    ai_max_output_tokens: int = 180
    ai_prompt_cache_key: str = "pars2ray-optimizer-v3"
    national_mode_enabled: bool = True
    national_failure_threshold: int = 3
    national_recovery_threshold: int = 2
    national_max_candidates_per_round: int = 30
    intelligence_interval_seconds: int = 300
    canary_auto_apply: bool = False
    panel_http_port: int = 8000

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, value: str) -> str:
        value = value.lower().strip()
        if value == "test":
            return "development"
        if value not in {"development", "staging", "production"}:
            raise ValueError("environment must be development, staging, or production")
        return value

    @model_validator(mode="after")
    def production_secrets_must_be_rotated(self):
        if self.environment == "production":
            if self.debug:
                raise ValueError("debug must be false in production")
            if self.jwt_secret == _DEV_JWT:
                raise ValueError("jwt_secret must be explicitly configured in production")
            if self.master_secret == _DEV_MASTER:
                raise ValueError("master_secret must be explicitly configured in production")
            if self.admin_password == _DEV_ADMIN:
                raise ValueError("admin_password must be explicitly configured in production")
            if self.cors_origin_list and any(origin == "*" for origin in self.cors_origin_list):
                raise ValueError("wildcard CORS is not allowed in production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def trusted_host_list(self) -> list[str]:
        return [x.strip() for x in self.trusted_hosts.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
