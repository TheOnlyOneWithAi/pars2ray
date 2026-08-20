from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "master/requirements.txt", ROOT / "agent/requirements.txt", ROOT / "installer/requirements.txt"]
PINNED = re.compile(r"^[A-Za-z0-9_.-]+(?:\[[^\]]+\])?==[^\s#]+(?:\s*#.*)?$")


def main() -> int:
    failures: list[str] = []
    for path in FILES:
        for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if not PINNED.fullmatch(line):
                failures.append(f"{path.relative_to(ROOT)}:{number}: dependency is not pinned with ==")
    if failures:
        print("\n".join(failures))
        return 1
    print(f"Dependency pin check passed for {len(FILES)} requirement files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
