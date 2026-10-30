"""Fresh-process guard for the frozen C4.3 current production modules."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import (
    actions,
    skills,
)


EXPECTED = {
    "actions.py": "f94afaed4e1d225eb15e48151436f2480b6701754b7be362b9a9b24bfc87bb6a",
    "skills.py": "2ce87fe45d8964ef5ef16bd76df8e2132a1f24d27fe5ae33192bb98e8678443c",
}


def main() -> None:
    repo = Path.cwd().resolve()
    assert repo == PROJECT_ROOT, (repo, PROJECT_ROOT)
    for name, module in (("actions.py", actions), ("skills.py", skills)):
        source = Path(module.__file__).resolve()
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        assert source.is_relative_to(repo), (name, source, repo)
        assert digest == EXPECTED[name], (name, digest, EXPECTED[name])
        print(f"{name} {digest} {source}")


if __name__ == "__main__":
    main()
