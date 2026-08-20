import math

from app.services.candidate_engine import generate
from app.services.validator import validate_candidate


def test_generate_empty_and_non_positive_limits():
    assert generate([], 10) == []
    assert generate(["n1"], 0) == []
    assert generate(["n1"], -1) == []


def test_generate_deduplicates_nodes_and_ids():
    candidates = generate([" n1 ", "n1", "n2"], 100)
    assert candidates
    assert len({item["candidate_id"] for item in candidates}) == len(candidates)
    assert all(item["path"][0] in {"n1", "n2"} for item in candidates)


def test_validator_rejects_nan_and_infinity():
    base = {"core": "xray", "protocol": "vless", "transport": "tcp"}
    assert not validate_candidate({**base, "score": math.nan}, 0).valid
    assert not validate_candidate({**base, "score": math.inf}, 0).valid
    assert not validate_candidate({**base, "score": 80}, math.inf).valid


def test_validator_rejects_non_numeric_score():
    candidate = {"core": "xray", "protocol": "vless", "transport": "tcp", "score": "bad"}
    assert validate_candidate(candidate, 0).reason == "invalid_score"
