from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Table, Text, Column, MetaData, select, insert, update, delete
from sqlalchemy.orm import Session


metadata = MetaData()

inbounds = Table(
    "inbound_profiles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), unique=True, nullable=False),
    Column("node_key", String(80), nullable=False, index=True),
    Column("core", String(32), nullable=False, default="xray"),
    Column("protocol", String(32), nullable=False),
    Column("port", Integer, nullable=False),
    Column("transport", String(32), nullable=False),
    Column("security", String(32), nullable=False, default="none"),
    Column("config_json", JSON, nullable=False),
    Column("score", Integer, nullable=False, default=0),
    Column("status", String(24), nullable=False, default="CANDIDATE"),
    Column("is_selected", Boolean, nullable=False, default=False),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)

clients = Table(
    "client_profiles",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("email", String(254), nullable=True),
    Column("uuid", String(64), unique=True, nullable=False, index=True),
    Column("inbound_ids", JSON, nullable=False, default=list),
    Column("enabled", Boolean, nullable=False, default=True),
    Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
)


def ensure_tables(engine) -> None:
    metadata.create_all(engine, checkfirst=True)


def list_inbounds(db: Session) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in db.execute(select(inbounds).order_by(inbounds.c.score.desc(), inbounds.c.id.desc())).all()]


def create_inbound(db: Session, data: dict[str, Any]) -> dict[str, Any]:
    result = db.execute(insert(inbounds).values(**data).returning(*inbounds.c))
    row = result.first()
    db.commit()
    return dict(row._mapping)


def select_inbound(db: Session, inbound_id: int) -> dict[str, Any] | None:
    row = db.execute(select(inbounds).where(inbounds.c.id == inbound_id)).first()
    return dict(row._mapping) if row else None


def mark_selected(db: Session, inbound_id: int) -> dict[str, Any] | None:
    row = select_inbound(db, inbound_id)
    if not row:
        return None
    db.execute(update(inbounds).values(is_selected=False).where(inbounds.c.node_key == row["node_key"]))
    db.execute(update(inbounds).values(is_selected=True, status="ACTIVE").where(inbounds.c.id == inbound_id))
    db.commit()
    return select_inbound(db, inbound_id)


def create_client(db: Session, name: str, email: str | None, inbound_ids: list[int]) -> dict[str, Any]:
    client = {
        "name": name.strip(),
        "email": email.strip() if email else None,
        "uuid": str(uuid.uuid4()),
        "inbound_ids": sorted(set(int(item) for item in inbound_ids)),
        "enabled": True,
        "created_at": datetime.utcnow(),
    }
    result = db.execute(insert(clients).values(**client).returning(*clients.c))
    row = result.first()
    db.commit()
    return dict(row._mapping)


def list_clients(db: Session) -> list[dict[str, Any]]:
    return [dict(row._mapping) for row in db.execute(select(clients).order_by(clients.c.id.desc())).all()]


def get_client(db: Session, client_id: int) -> dict[str, Any] | None:
    row = db.execute(select(clients).where(clients.c.id == client_id)).first()
    return dict(row._mapping) if row else None


def delete_client(db: Session, client_id: int) -> bool:
    result = db.execute(delete(clients).where(clients.c.id == client_id))
    db.commit()
    return bool(result.rowcount)
