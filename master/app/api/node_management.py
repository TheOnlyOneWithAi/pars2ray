from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user, request_ip, require_roles
from app.core.security import encrypt_secret, token_hash
from app.db.base import get_db
from app.models.entities import Node, User
from app.services.audit import record
from app.services.ssh_provision import SSHConfig, provision as provision_over_ssh, test as test_ssh

router = APIRouter(prefix="/api/v1/node-management", tags=["node-management"])


class SSHRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=128)
    host_key_fingerprint: str = Field(min_length=10, max_length=128)
    password: str | None = Field(default=None, max_length=4096)
    private_key: str | None = Field(default=None, max_length=20000)
    passphrase: str | None = Field(default=None, max_length=4096)

    @field_validator("host", "username", "host_key_fingerprint")
    @classmethod
    def clean(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ch.isspace() for ch in value) and not value.startswith("SHA256:"):
            raise ValueError("invalid_ssh_value")
        return value

    def to_config(self) -> SSHConfig:
        if not self.password and not self.private_key:
            raise ValueError("ssh_password_or_private_key_required")
        return SSHConfig(host=self.host, port=self.port, username=self.username, host_key_fingerprint=self.host_key_fingerprint, password=self.password, private_key=self.private_key, passphrase=self.passphrase)


class NodeProvisionRequest(BaseModel):
    node_key: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z]{2}\d{0,3}$")
    country: str = Field(min_length=2, max_length=2)
    endpoint: str = Field(min_length=8, max_length=255)
    ssh: SSHRequest

    @field_validator("node_key", "country")
    @classmethod
    def uppercase(cls, value: str) -> str:
        return value.upper()

    @field_validator("endpoint")
    @classmethod
    def valid_endpoint(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("endpoint must use http or https")
        return value


@router.post("/test-ssh", dependencies=[Depends(require_roles("SUPER_ADMIN", "ADMIN"))])
def test_ssh_connection(payload: SSHRequest) -> dict:
    try:
        return test_ssh(payload.to_config())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"ssh_connection_failed:{exc}") from exc


@router.post("", dependencies=[Depends(require_roles("SUPER_ADMIN", "ADMIN"))])
def provision_node(payload: NodeProvisionRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    if db.scalar(select(Node).where(Node.node_key == payload.node_key)):
        raise HTTPException(status_code=409, detail="node_key_exists")
    try:
        ssh_config = payload.ssh.to_config()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    agent_token = secrets.token_urlsafe(48)
    node = Node(node_key=payload.node_key, country=payload.country, endpoint=payload.endpoint, agent_token_hash=token_hash(agent_token), agent_token_enc=encrypt_secret(agent_token), ssh_config_enc=encrypt_secret(json.dumps(payload.ssh.model_dump(exclude_none=True), separators=(",", ":"))), status="PROVISIONING", agent_version="unknown")
    db.add(node)
    db.flush()
    try:
        provision_over_ssh(ssh_config, payload.node_key, payload.country, agent_token)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"node_provision_failed:{exc}") from exc
    node.status = "REGISTERED"
    record(db, user, "node.provision", "node", str(node.id), request_ip(request))
    db.commit()
    return {"id": node.id, "node_key": node.node_key, "country": node.country, "endpoint": node.endpoint, "status": node.status, "agent_version": node.agent_version, "provisioned": True}
