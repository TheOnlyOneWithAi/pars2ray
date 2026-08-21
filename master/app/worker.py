from __future__ import annotations

import logging
import os
import tempfile
import time
from pathlib import Path

from sqlalchemy import delete

from app.core.config import settings
from app.core.security import utcnow
from app.db.base import SessionLocal
from app.models.entities import RefreshToken

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pars2ray.worker")

# Use a process-private temporary directory instead of a predictable filename
# directly under /tmp. This removes the symlink/race risk flagged by Bandit B108
# while keeping the marker disposable and outside application data.
_WORKER_RUNTIME_DIR = Path(tempfile.mkdtemp(prefix="pars2ray-worker-"))
WORKER_READY_MARKER = _WORKER_RUNTIME_DIR / "ready"


def cleanup() -> int:
    db = SessionLocal()
    try:
        result = db.execute(delete(RefreshToken).where(RefreshToken.expires_at < utcnow()))
        db.commit()
        return result.rowcount or 0
    finally:
        db.close()


def main() -> None:
    WORKER_READY_MARKER.touch(exist_ok=True)
    log.info("worker ready; marker=%s", WORKER_READY_MARKER)
    try:
        while True:
            try:
                removed = cleanup()
                if removed:
                    log.info("removed %s expired refresh tokens", removed)
            except Exception:
                log.exception("worker cycle failed")
            time.sleep(max(settings.worker_poll_seconds, 10))
    finally:
        try:
            WORKER_READY_MARKER.unlink(missing_ok=True)
            _WORKER_RUNTIME_DIR.rmdir()
        except OSError:
            log.debug("could not remove worker runtime directory", exc_info=True)


if __name__ == "__main__":
    main()
