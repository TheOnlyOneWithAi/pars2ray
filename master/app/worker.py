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
    while True:
        try:
            removed = cleanup()
            if removed:
                log.info("removed %s expired refresh tokens", removed)
            # Readiness is intentionally one-shot. Once the worker has completed
            # one successful DB cycle, Docker keeps it healthy until restart.
            WORKER_READY_MARKER.touch(exist_ok=True)
        except Exception:
            log.exception("worker cycle failed")
        time.sleep(max(settings.worker_poll_seconds, 10))


if __name__ == "__main__":
    main()
