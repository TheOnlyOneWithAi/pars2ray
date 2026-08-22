from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Protocol


class TrafficSample(Protocol):
    node_id: int
    rx_bytes: int
    tx_bytes: int
    sampled_at: datetime


def _utc(value: datetime) -> datetime:
    """Normalize aware and naive timestamps to naive UTC for comparison."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _utc_hour(value: datetime) -> datetime:
    return _utc(value).replace(minute=0, second=0, microsecond=0)


def hourly_traffic(samples: Iterable[TrafficSample]) -> list[dict[str, int | str]]:
    """Aggregate cumulative node counters into hourly traffic deltas."""
    normalized = [(_utc(sample.sampled_at), sample) for sample in samples]
    ordered = sorted(normalized, key=lambda item: (int(item[1].node_id), item[0]))
    buckets: dict[datetime, dict[str, int]] = {}
    previous: dict[int, tuple[int, int]] = {}

    for sampled_at, sample in ordered:
        node_id = int(sample.node_id)
        rx = max(int(sample.rx_bytes), 0)
        tx = max(int(sample.tx_bytes), 0)
        previous_sample = previous.get(node_id)
        if previous_sample is None:
            delta_rx = 0
            delta_tx = 0
        else:
            prev_rx, prev_tx = previous_sample
            delta_rx = rx - prev_rx if rx >= prev_rx else 0
            delta_tx = tx - prev_tx if tx >= prev_tx else 0
        previous[node_id] = (rx, tx)

        hour = sampled_at.replace(minute=0, second=0, microsecond=0)
        bucket = buckets.setdefault(hour, {"rx_bytes": 0, "tx_bytes": 0, "samples": 0})
        bucket["rx_bytes"] += delta_rx
        bucket["tx_bytes"] += delta_tx
        bucket["samples"] += 1

    return [
        {"timestamp": hour.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"), **buckets[hour]}
        for hour in sorted(buckets)
    ]
