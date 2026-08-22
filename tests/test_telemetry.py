from dataclasses import dataclass
from datetime import datetime

from app.services.telemetry import hourly_traffic


@dataclass
class Sample:
    node_id: int
    rx_bytes: int
    tx_bytes: int
    sampled_at: datetime


def test_hourly_traffic_aggregates_cumulative_deltas_per_node():
    rows = [
        Sample(1, 30, 20, datetime(2026, 8, 19, 11, 55)),
        Sample(1, 10, 5, datetime(2026, 8, 19, 10, 15)),
        Sample(1, 15, 7, datetime(2026, 8, 19, 10, 45)),
    ]

    result = hourly_traffic(rows)

    assert result == [
        {"timestamp": "2026-08-19T10:00:00Z", "rx_bytes": 5, "tx_bytes": 2, "samples": 2},
        {"timestamp": "2026-08-19T11:00:00Z", "rx_bytes": 15, "tx_bytes": 13, "samples": 1},
    ]


def test_hourly_traffic_tracks_nodes_independently():
    rows = [
        Sample(1, 100, 50, datetime(2026, 8, 19, 10, 0)),
        Sample(2, 200, 80, datetime(2026, 8, 19, 10, 1)),
        Sample(1, 130, 70, datetime(2026, 8, 19, 10, 2)),
        Sample(2, 230, 100, datetime(2026, 8, 19, 10, 3)),
    ]

    result = hourly_traffic(rows)

    assert result == [
        {"timestamp": "2026-08-19T10:00:00Z", "rx_bytes": 60, "tx_bytes": 40, "samples": 4}
    ]


def test_hourly_traffic_treats_counter_reset_as_new_baseline():
    rows = [
        Sample(1, 100, 50, datetime(2026, 8, 19, 10, 0)),
        Sample(1, 130, 70, datetime(2026, 8, 19, 10, 1)),
        Sample(1, 10, 5, datetime(2026, 8, 19, 10, 2)),
        Sample(1, 25, 12, datetime(2026, 8, 19, 10, 3)),
    ]

    result = hourly_traffic(rows)

    assert result == [
        {"timestamp": "2026-08-19T10:00:00Z", "rx_bytes": 45, "tx_bytes": 27, "samples": 4}
    ]


def test_hourly_traffic_never_exposes_negative_counters():
    result = hourly_traffic([Sample(1, -1, -2, datetime(2026, 8, 19, 10, 15))])
    assert result[0]["rx_bytes"] == 0
    assert result[0]["tx_bytes"] == 0
