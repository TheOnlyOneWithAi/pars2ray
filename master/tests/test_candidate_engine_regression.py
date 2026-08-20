from app.services.candidate_engine import generate


def test_generate_normalizes_deduplicates_and_respects_limit():
    candidates = generate([" node-a ", "node-a", "", "node-b"], max_candidates=5)

    assert len(candidates) == 5
    assert all(candidate["path"] in (["node-a"], ["node-b"]) for candidate in candidates)
    assert len({candidate["candidate_id"] for candidate in candidates}) == len(candidates)
    assert all(candidate["candidate_id"] for candidate in candidates)


def test_generate_is_deterministic():
    first = generate(["node-a", "node-b"], max_candidates=20)
    second = generate(["node-a", "node-b"], max_candidates=20)

    assert first == second


def test_generate_zero_negative_and_empty_inputs():
    assert generate([], max_candidates=10) == []
    assert generate(["node"], max_candidates=0) == []
    assert generate(["node"], max_candidates=-1) == []
    assert generate(["", "   "], max_candidates=10) == []


def test_experimental_transport_switch_is_explicit():
    stable = generate(["node"], max_candidates=100, allow_experimental=False)
    experimental = generate(["node"], max_candidates=100, allow_experimental=True)

    stable_transports = {candidate["transport"] for candidate in stable}
    experimental_transports = {candidate["transport"] for candidate in experimental}
    assert stable_transports == {"tcp", "grpc", "xhttp"}
    assert experimental_transports == {"tcp", "grpc", "websocket", "httpupgrade", "xhttp"}
