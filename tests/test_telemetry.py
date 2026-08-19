from dataclasses import dataclass
from datetime import datetime

from app.services.telemetry import hourly_traffic


@dataclass
class Sample:
    rx_bytes: int
    tx_bytes: int
    sampled_at: datetime


def test_hourly_traffic_aggregates_and_orders_samples():
    rows = [
        Sample(30, 20, datetime(2026, 8, 19, 11, 55)),
        Sample(10, 5, datetime(2026, 8, 19, 10, 15)),
        Sample(15, 7, datetime(2026, 8, 19, 10, 45)),
    ]

    result = hourly_traffic(rows)

    assert result == [
        {"timestamp": "2026-08-19T10:00:00Z", "rx_bytes": 25, "tx_bytes": 12, "samples": 2},
        {"timestamp": "2026-08-19T11:00:00Z", "rx_bytes": 30, "tx_bytes": 20, "samples": 1},
    ]


def test_hourly_traffic_never_exposes_negative_counters():
    result = hourly_traffic([Sample(-1, -2, datetime(2026, 8, 19, 10, 15))])
    assert result[0]["rx_bytes"] == 0
    assert result[0]["tx_bytes"] == 0
