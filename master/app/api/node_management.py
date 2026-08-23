from __future__ import annotations

import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_user, request_ip, require_roles
from app.core.security import decrypt_secret, encrypt_secret, token_hash
from app.db.base import get_db
from app.models.entities import Node, User
from app.services import agent_client
from app.services.audit import record
from app.services.ssh_provision import SSHConfig, provision as provision_over_ssh, test as test_ssh

router = APIRouter(prefix="/api/v1/node-management", tags=["node-management"])


class SSHRequest(BaseModel):
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(default="", max_length=4096)

    @field_validator("host", "username")
    @classmethod
    def clean(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ch.isspace() for ch in value):
            raise ValueError("invalid_ssh_value")
        return value

    def to_config(self) -> SSHConfig:
        return SSHConfig(host=self.host, port=self.port, username=self.username, password=self.password or None)


class NodeProvisionRequest(BaseModel):
    """Operator-facing node definition: SSH is the source of truth."""

    node_key: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z]{2}\d{0,3}$")
    country: str = Field(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    ssh: SSHRequest

    @field_validator("node_key", "country")
    @classmethod
    def uppercase(cls, value: str) -> str:
        return value.upper()


class NodeUpdateRequest(BaseModel):
    """Only mutable operator-owned metadata and SSH credentials are accepted.

    The agent endpoint is deliberately not configurable from the panel. It is
    derived from the SSH-managed node installation and is an internal detail.
    """

    country: str | None = Field(default=None, min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    ssh: SSHRequest | None = None

    @field_validator("country")
    @classmethod
    def uppercase_country(cls, value: str | None) -> str | None:
        return value.upper() if value else value


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

    ssh_config = payload.ssh.to_config()
    # Internal agent address only; operators never have to supply or maintain it.
    endpoint = f"http://{payload.ssh.host}:9100"
    agent_token = secrets.token_urlsafe(48)
    node = Node(
        node_key=payload.node_key,
        country=payload.country,
        endpoint=endpoint,
        agent_token_hash=token_hash(agent_token),
        agent_token_enc=encrypt_secret(agent_token),
        ssh_config_enc=encrypt_secret(json.dumps(payload.ssh.model_dump(), separators=(",", ":"))),
        status="PROVISIONING",
        agent_version="unknown",
    )
    db.add(node)
    try:
        # Persist first so a long/failed SSH installation can never make the
        # node disappear from the managed-node inventory.
        db.commit()
        db.refresh(node)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="node_key_exists") from exc

    node_id = node.id
    try:
        provision_over_ssh(ssh_config, payload.node_key, payload.country, agent_token)
    except Exception as exc:
        failed_node = db.get(Node, node_id)
        if failed_node is not None:
            failed_node.status = "FAILED"
            db.commit()
        raise HTTPException(status_code=502, detail=f"node_provision_failed:{exc}") from exc

    node = db.get(Node, node_id)
    if node is None:
        raise HTTPException(status_code=500, detail="node_persistence_lost")
    node.status = "REGISTERED"
    node.agent_version = "2.3.0"
    record(db, user, "node.provision", "node", str(node.id), request_ip(request))
    db.commit()
    return {
        "id": node.id,
        "node_key": node.node_key,
        "country": node.country,
        "status": node.status,
        "agent_version": node.agent_version,
        "ssh_managed": True,
        "provisioned": True,
    }


@router.patch("/{node_key}", dependencies=[Depends(require_roles("SUPER_ADMIN", "ADMIN"))])
def update_node(node_key: str, payload: NodeUpdateRequest, request: Request, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    node = db.scalar(select(Node).where(Node.node_key == node_key))
    if not node:
        raise HTTPException(status_code=404, detail="node_not_found")

    # SSH is the source of truth. Changing the SSH target/credentials without
    # reinstalling the agent leaves the database pointing at a host that does
    # not possess this node's token. Provision the new target first and only
    # then switch the persisted management state, so a failed update cannot
    # destroy a healthy existing node.
    if payload.ssh is not None:
        ssh_config = payload.ssh.to_config()
        country = payload.country or node.country
        try:
            agent_token = decrypt_secret(node.agent_token_enc)
            provision_over_ssh(ssh_config, node.node_key, country, agent_token)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"node_reprovision_failed:{exc}") from exc

        node.ssh_config_enc = encrypt_secret(json.dumps(payload.ssh.model_dump(), separators=(",", ":")))
        node.endpoint = f"http://{payload.ssh.host}:9100"
        node.agent_version = "2.3.0"
        node.status = "REGISTERED"

    if payload.country is not None:
        node.country = payload.country

    record(db, user, "node.update", "node", str(node.id), request_ip(request))
    db.commit()
    db.refresh(node)
    return {
        "id": node.id,
        "node_key": node.node_key,
        "country": node.country,
        "status": node.status,
        "agent_version": node.agent_version,
        "ssh_managed": True,
    }


@router.post("/{node_key}/probe", dependencies=[Depends(require_roles("SUPER_ADMIN", "ADMIN", "OPERATOR"))])
async def probe_node(node_key: str, db: Session = Depends(get_db)) -> dict:
    node = db.scalar(select(Node).where(Node.node_key == node_key))
    if not node:
        raise HTTPException(status_code=404, detail="node_not_found")
    was_draining = node.status == "DRAINING"
    try:
        result = await agent_client.health(node)
        node.status = "DRAINING" if was_draining else "ONLINE"
        from app.core.security import utcnow
        node.last_seen_at = utcnow()
        db.commit()
        return {"ok": True, "node_key": node.node_key, "status": node.status, "agent": result}
    except Exception as exc:
        if not was_draining:
            node.status = "OFFLINE"
        db.commit()
        return {"ok": False, "node_key": node.node_key, "status": node.status, "error": str(exc)}
