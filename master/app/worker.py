from __future__ import annotations

import logging
import time
from pathlib import Path

from sqlalchemy import delete

from app.core.config import settings
from app.core.security import utcnow
from app.db.base import SessionLocal
from app.models.entities import RefreshToken

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pars2ray.worker")
WORKER_READY_MARKER = Path("/tmp/.pars2ray-worker-ready")


def cleanup() -> int:
    db = SessionLocal()
    try:
        result = db.execute(delete(RefreshToken).where(RefreshToken.expires_at < utcnow()))
        db.commit()
        return result.rowcount or 0
    finally:
        db.close()


def main() -> None:
    # The Compose healthcheck is deliberately a one-shot lifecycle marker.
    # Dependency readiness is already enforced by Compose before the worker
    # starts, so once this process has started it is considered running/healthy.
    WORKER_READY_MARKER.touch(exist_ok=True)
    while True:
        try:
            removed = cleanup()
            if removed:
                log.info("removed %s expired refresh tokens", removed)
        except Exception:
            log.exception("worker cycle failed")
        time.sleep(max(settings.worker_poll_seconds, 10))


if __name__ == "__main__":
    main()
