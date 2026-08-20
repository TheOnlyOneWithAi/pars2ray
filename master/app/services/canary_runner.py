from __future__ import annotations

from dataclasses import dataclass

from app.services.experiment_lab import ExperimentPolicy
from app.services.network_intelligence import score_metrics


@dataclass(frozen=True)
class CanaryObservation:
    candidate_id: str
    latency_ms: float
    jitter_ms: float
    packet_loss_percent: float
    throughput_mbps: float
    stability_percent: float
    availability_percent: float = 100.0

    @property
    def score(self) -> float:
        metrics = score_metrics(self.latency_ms, self.jitter_ms, self.packet_loss_percent, self.throughput_mbps, self.stability_percent, self.availability_percent)
        return metrics.total


@dataclass(frozen=True)
class CanaryResult:
    candidate_id: str
    score: float
    action: str
    safe_to_promote: bool
    reason: str


class CanaryRunner:
    """Pure canary evaluation layer; transport mutation stays behind the production gate."""

    def __init__(self, policy: ExperimentPolicy | None = None) -> None:
        self.policy = policy or ExperimentPolicy()

    def evaluate(self, current_score: float, observation: CanaryObservation, consecutive_wins: int) -> CanaryResult:
        score = observation.score
        action = self.policy.decision(current_score, score, observation.packet_loss_percent, consecutive_wins, observation.stability_percent)
        if action == "PROMOTE":
            return CanaryResult(observation.candidate_id, score, action, True, "Candidate cleared deterministic promotion gates.")
        if action == "CANARY":
            return CanaryResult(observation.candidate_id, score, action, False, "Candidate improved the score but needs more successful canary observations.")
        if action == "ROLLBACK":
            return CanaryResult(observation.candidate_id, score, action, False, "Candidate breached loss or stability safety limits.")
        return CanaryResult(observation.candidate_id, score, action, False, "Candidate did not provide the required improvement.")
