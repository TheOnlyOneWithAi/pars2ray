from datetime import datetime, timezone
from pathlib import Path

from app.services.telemetry import hourly_traffic


def test_telemetry_uses_counter_deltas_not_cumulative_sums() -> None:
    class Sample:
        def __init__(self, node_id, rx_bytes, tx_bytes, sampled_at):
            self.node_id = node_id
            self.rx_bytes = rx_bytes
            self.tx_bytes = tx_bytes
            self.sampled_at = sampled_at

    rows = [
        Sample(1, 1000, 500, datetime(2026, 8, 23, 10, 0, tzinfo=timezone.utc)),
        Sample(1, 1300, 700, datetime(2026, 8, 23, 10, 1, tzinfo=timezone.utc)),
    ]
    result = hourly_traffic(rows)
    assert result[0]["rx_bytes"] == 300
    assert result[0]["tx_bytes"] == 200


def test_node_schema_exposes_runtime_fields_used_by_frontend() -> None:
    from app.schemas import NodeOut

    assert "latency_ms" in NodeOut.model_fields
    assert "agent_version" in NodeOut.model_fields


def test_frontend_does_not_regress_to_operator_endpoint_configuration() -> None:
    source = (Path(__file__).resolve().parents[1] / "frontend/src/api.ts").read_text(encoding="utf-8")
    assert "endpoint?:string" not in source
