from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Protocol


class TrafficSample(Protocol):
    node_id: int
    rx_bytes: int
    tx_bytes: int
    sampled_at: datetime


def _utc_hour(value: datetime) -> datetime:
    """Normalize a sample timestamp to a naive UTC hour for DB compatibility."""
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(minute=0, second=0, microsecond=0)


def hourly_traffic(samples: Iterable[TrafficSample]) -> list[dict[str, int | str]]:
    """Aggregate cumulative node counters into hourly traffic deltas.

    Agent metrics are cumulative counters, so summing raw samples would
    over-count traffic. Counters are tracked independently per node; a
    counter reset/restart is treated as a new baseline rather than negative
    traffic.
    """
    ordered = sorted(samples, key=lambda sample: (sample.node_id, sample.sampled_at))
    buckets: dict[datetime, dict[str, int]] = {}
    previous: dict[int, tuple[int, int]] = {}

    for sample in ordered:
        node_id = int(sample.node_id)
        rx = max(int(sample.rx_bytes), 0)
        tx = max(int(sample.tx_bytes), 0)
        prev_rx, prev_tx = previous.get(node_id, (rx, tx))
        delta_rx = rx - prev_rx if rx >= prev_rx else 0
        delta_tx = tx - prev_tx if tx >= prev_tx else 0
        previous[node_id] = (rx, tx)

        hour = _utc_hour(sample.sampled_at)
        bucket = buckets.setdefault(hour, {"rx_bytes": 0, "tx_bytes": 0, "samples": 0})
        bucket["rx_bytes"] += delta_rx
        bucket["tx_bytes"] += delta_tx
        bucket["samples"] += 1

    return [
        {"timestamp": hour.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"), **buckets[hour]}
        for hour in sorted(buckets)
    ]
