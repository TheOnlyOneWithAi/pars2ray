from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol


class TrafficSample(Protocol):
    rx_bytes: int
    tx_bytes: int
    sampled_at: datetime


def hourly_traffic(samples: Iterable[TrafficSample]) -> list[dict[str, int | str]]:
    """Aggregate persisted traffic counters into stable UTC hourly buckets."""
    buckets: dict[datetime, dict[str, int]] = {}
    for sample in samples:
        hour = sample.sampled_at.replace(minute=0, second=0, microsecond=0)
        bucket = buckets.setdefault(hour, {"rx_bytes": 0, "tx_bytes": 0, "samples": 0})
        bucket["rx_bytes"] += max(int(sample.rx_bytes), 0)
        bucket["tx_bytes"] += max(int(sample.tx_bytes), 0)
        bucket["samples"] += 1
    return [
        {"timestamp": hour.isoformat() + "Z", **buckets[hour]}
        for hour in sorted(buckets)
    ]
