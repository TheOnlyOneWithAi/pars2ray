from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, random_token, token_hash, utcnow, verify_password
from app.models.entities import RefreshToken, Role, User


ROLE_NAMES = ["SUPER_ADMIN", "ADMIN", "OPERATOR", "RESELLER", "USER"]


def ensure_seed(db: Session) -> None:
    roles = {r.name: r for r in db.scalars(select(Role)).all()}
    for name in ROLE_NAMES:
        if name not in roles:
            roles[name] = Role(name=name, description=name.replace("_", " ").title())
            db.add(roles[name])
    db.flush()

    admin = db.scalar(select(User).where(User.username == settings.admin_user))
    if not admin:
        admin = User(
            username=settings.admin_user,
            email=settings.admin_email,
            password_hash=hash_password(settings.admin_password),
        )
        admin.roles = [roles["SUPER_ADMIN"]]
        db.add(admin)
    else:
        # The installer/SSH CLI persists the canonical admin password in
        # ADMIN_PASSWORD before restarting the master. Keep the runtime DB
        # synchronized with that value so the process and CLI cannot drift
        # to different credentials after a restart.
        if settings.admin_password and not verify_password(settings.admin_password, admin.password_hash):
            admin.password_hash = hash_password(settings.admin_password)
        if admin.email != settings.admin_email:
            admin.email = settings.admin_email
        if not admin.is_active:
            admin.is_active = True
        if not admin.roles:
            admin.roles = [roles["SUPER_ADMIN"]]

    db.commit()


def authenticate(db: Session, username: str, password: str) -> User | None:
    user = db.scalar(select(User).where(User.username == username, User.is_active.is_(True)))
    return user if user and verify_password(password, user.password_hash) else None


def issue_tokens(db: Session, user: User) -> tuple[str, str, int]:
    access, ttl = create_access_token(user.username, user.role)
    refresh = random_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash(refresh), expires_at=utcnow() + timedelta(days=settings.refresh_token_days)))
    user.last_login_at = utcnow()
    db.commit()
    return access, refresh, ttl


def rotate_refresh(db: Session, raw_refresh: str) -> tuple[User, str, str, int] | None:
    stored = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(raw_refresh), RefreshToken.revoked_at.is_(None)))
    if not stored or stored.expires_at <= utcnow():
        return None
    user = db.get(User, stored.user_id)
    if not user or not user.is_active:
        return None
    stored.revoked_at = utcnow()
    access, refresh, ttl = issue_tokens(db, user)
    return user, access, refresh, ttl
