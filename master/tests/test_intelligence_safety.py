import pytest

from app.services.canary_runner import CanaryObservation, CanaryRunner
from app.services.experiment_lab import ExperimentPolicy


def test_loss_breach_rolls_back():
    result = CanaryRunner().evaluate(80, CanaryObservation("c1", 60, 5, 6, 100, 99), 5)
    assert result.action == "ROLLBACK"
    assert result.safe_to_promote is False


def test_low_stability_rolls_back():
    result = CanaryRunner().evaluate(80, CanaryObservation("c1", 60, 5, 1, 100, 90), 5)
    assert result.action == "ROLLBACK"


def test_improvement_needs_more_wins():
    result = CanaryRunner().evaluate(50, CanaryObservation("c1", 40, 4, 0.1, 100, 99), 1)
    assert result.action == "CANARY"
    assert result.safe_to_promote is False


def test_policy_promotes_only_after_gates():
    policy = ExperimentPolicy()
    assert policy.decision(50, 65, 1, 3, 99) == "PROMOTE"
    assert policy.decision(50, 55, 1, 3, 99) == "KEEP"
