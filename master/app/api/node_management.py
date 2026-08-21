from __future__ import annotations

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

router = APIRouter(prefix="/api/v1/node-management", tags=["node-management"])


class NodeProvisionRequest(BaseModel):
    node_key: str = Field(min_length=2, max_length=40, pattern=r"^[A-Z]{2}\d{0,3}$")
    country: str = Field(min_length=2, max_length=2)
    endpoint: str = Field(min_length=8, max_length=255)

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


@router.post("", dependencies=[Depends(require_roles("SUPER_ADMIN", "ADMIN"))])
def provision_node(
    payload: NodeProvisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    if db.scalar(select(Node).where(Node.node_key == payload.node_key)):
        raise HTTPException(status_code=409, detail="node_key_exists")

    agent_token = secrets.token_urlsafe(48)
    node = Node(
        node_key=payload.node_key,
        country=payload.country,
        endpoint=payload.endpoint,
        agent_token_hash=token_hash(agent_token),
        agent_token_enc=encrypt_secret(agent_token),
        status="PENDING",
        agent_version="unknown",
    )
    db.add(node)
    db.flush()
    record(db, user, "node.provision", "node", str(node.id), request_ip(request))
    db.commit()

    return {
        "id": node.id,
        "node_key": node.node_key,
        "country": node.country,
        "endpoint": node.endpoint,
        "status": node.status,
        "agent_token": agent_token,
        "agent_url": f"{node.endpoint}/health",
        "install": {
            "node_key": node.node_key,
            "country": node.country,
            "endpoint": node.endpoint,
            "agent_token": agent_token,
        },
    }
