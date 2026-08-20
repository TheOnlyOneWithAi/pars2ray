from __future__ import annotations

from dataclasses import dataclass

from app.services import agent_client


@dataclass(frozen=True)
class HealthObservation:
    node_id: int
    online: bool
    latency_ms: float
    jitter_ms: float
    packet_loss_percent: float
    stability_percent: float
    availability_percent: float
    throughput_mbps: float


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


async def probe_node(node) -> HealthObservation:
    """Collect a normalized health snapshot; never mutates node configuration."""
    try:
        await agent_client.health(node)
        metrics = await agent_client.metrics(node)
        return HealthObservation(
            node_id=node.id,
            online=True,
            latency_ms=_number(metrics.get("latency_ms")),
            jitter_ms=_number(metrics.get("jitter_ms")),
            packet_loss_percent=_number(metrics.get("packet_loss_percent")),
            stability_percent=_number(metrics.get("stability_percent"), 100.0),
            availability_percent=_number(metrics.get("availability_percent"), 100.0),
            throughput_mbps=_number(metrics.get("throughput_mbps")),
        )
    except Exception:
        return HealthObservation(node.id, False, 9999.0, 9999.0, 100.0, 0.0, 0.0, 0.0)
