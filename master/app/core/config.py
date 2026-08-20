from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False)

    app_name: str = "Pars2Ray Enterprise"
    app_version: str = "2.2.0"
    environment: str = "production"
    debug: bool = False
    database_url: str = "postgresql+psycopg://pars2ray:change-me@db:5432/pars2ray"
    redis_url: str = "redis://redis:6379/0"
    jwt_secret: str = Field(default="dev-only-change-jwt-secret-please-rotate", min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    master_secret: str = Field(default="dev-only-change-master-secret-please-rotate", min_length=32)
    admin_user: str = "admin"
    admin_password: str = Field(default="dev-admin-password-change-me", min_length=12)
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
    panel_http_port: int = 8000

    @field_validator("environment")
    @classmethod
    def valid_environment(cls, value: str) -> str:
        if value not in {"development", "staging", "production"}:
            raise ValueError("environment must be development, staging, or production")
        return value

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
