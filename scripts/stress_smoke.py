from __future__ import annotations

import concurrent.futures
import sys
import time

sys.path.insert(0, "master")

from app.services.candidate_engine import generate


NODES = [f"node-{i:03d}" for i in range(100)]
ITERATIONS = 200
WORKERS = 16


def one_run(_: int) -> int:
    started = time.perf_counter()
    candidates = generate(NODES, max_candidates=1000, allow_experimental=True)
    assert len(candidates) == 1000
    ids = [candidate["candidate_id"] for candidate in candidates]
    assert len(ids) == len(set(ids))
    assert all(candidate["path"] and candidate["path"][0] in NODES for candidate in candidates)
    assert time.perf_counter() - started < 5.0
    return len(candidates)


def main() -> int:
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        results = list(pool.map(one_run, range(ITERATIONS)))
    assert sum(results) == ITERATIONS * 1000
    print(f"Stress smoke passed: {ITERATIONS} runs, {WORKERS} workers, {sum(results)} candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
