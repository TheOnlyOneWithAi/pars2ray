from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from app.services.intelligence_cycle import run_intelligence_cycle

logger = logging.getLogger(__name__)


class IntelligenceScheduler:
    """Single-flight scheduler for bounded intelligence cycles."""

    def __init__(self, interval_seconds: int = 300) -> None:
        self.interval_seconds = max(30, int(interval_seconds))
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._running

    async def run_once(self):
        return await run_intelligence_cycle()

    async def _loop(self) -> None:
        while self._running:
            try:
                decision = await self.run_once()
                logger.info("intelligence cycle: action=%s candidate=%s", decision.action, decision.candidate_id)
            except Exception:
                logger.exception("intelligence cycle failed; next cycle will retry")
            try:
                await asyncio.sleep(self.interval_seconds)
            except asyncio.CancelledError:
                break

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="pars2ray-intelligence")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
