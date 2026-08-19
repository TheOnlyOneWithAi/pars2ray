from sqlalchemy.orm import Session

from app.models.entities import AuditLog, User


def record(db: Session, actor: User | None, action: str, resource_type: str = "", resource_id: str = "", ip_address: str = "", metadata: dict | None = None) -> None:
    db.add(AuditLog(actor_user_id=actor.id if actor else None, action=action, resource_type=resource_type, resource_id=resource_id, ip_address=ip_address, metadata_json=metadata or {}))
