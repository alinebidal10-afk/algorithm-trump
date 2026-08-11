"""
asu_baseline.py
----------------
Phase step A1: measurement-only baseline for ASUValueV1 (seat 0) against the
three scripted opponents (TheHoarder, TheDealMaker, TheGambler), for seeds
3, 7, 11, over the first 300 engine steps (or until the game ends).

For every seat-0 `decide()` result, the record is canonicalized to JSON and
chained into a running SHA-256 digest (one digest per seed). Only the seat-0
`decide()` calls are timed.

This script performs NO optimisation and NO changes to ASU_FROZEN_TEACHER/ or
monopoly_game_engine/ — it is pure measurement tooling.

Usage:
    .venv/bin/python tools/asu_baseline.py
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ASU_FROZEN_TEACHER.core import ASUValueV1  # noqa: E402
from ASU_FROZEN_TEACHER.evaluate import (  # noqa: E402
    _ScriptedAdapter,
    _new_seeded_game,
)
from ASU_FROZEN_TEACHER.spec import FROZEN_SPEC_HASH  # noqa: E402
from monopoly_game_engine.agents_fixed import FP_AGENT_CLASSES  # noqa: E402

SEEDS = (3, 7, 11)
MAX_STEPS = 300
ARTIFACTS_DIR = ROOT / "artifacts"
OUTPUT_PATH = ARTIFACTS_DIR / "asu_baseline.json"


def canonical_json(record: dict[str, Any]) -> str:
    """Canonical JSON: sorted keys, compact separators, RAW float repr.

    No rounding, no custom float formatting — Python's default float
    serialisation in json.dumps is the shortest round-trip repr.
    """
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


def run_seed(seed: int) -> dict[str, Any]:
    game = _new_seeded_game(seed)
    env = game.env

    seat0 = ASUValueV1(0)
    opponents = {
        1: _ScriptedAdapter(FP_AGENT_CLASSES[0](1), 1),  # TheHoarder
        2: _ScriptedAdapter(FP_AGENT_CLASSES[1](2), 2),  # TheDealMaker
        3: _ScriptedAdapter(FP_AGENT_CLASSES[2](3), 3),  # TheGambler
    }

    digest = hashlib.sha256()
    decisions = 0
    total_seconds = 0.0
    steps = 0

    while steps < MAX_STEPS and not env.done:
        actor = env.whose_turn()
        if actor == 0:
            started = time.perf_counter()
            decision = seat0.decide(env)
            elapsed = time.perf_counter() - started
            total_seconds += elapsed
            decisions += 1

            record = decision.to_dict()
            digest.update(canonical_json(record).encode("utf-8"))

            action = decision.selected_action
        else:
            action = opponents[actor].choose_action(env)

        game.step(action)
        steps += 1

    return {
        "digest": digest.hexdigest(),
        "decisions": decisions,
        "steps": steps,
        "seconds": total_seconds,
        "seconds_per_decision": (total_seconds / decisions) if decisions else None,
    }


def main() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    per_seed: dict[str, Any] = {}
    total_seconds = 0.0
    total_decisions = 0

    for seed in SEEDS:
        result = run_seed(seed)
        per_seed[str(seed)] = result
        total_seconds += result["seconds"]
        total_decisions += result["decisions"]

    aggregate_seconds_per_decision = (
        total_seconds / total_decisions if total_decisions else None
    )

    payload = {
        "frozen_spec_hash": FROZEN_SPEC_HASH,
        "python_version": platform.python_version(),
        "seeds": per_seed,
        "aggregate_seconds_per_decision": aggregate_seconds_per_decision,
    }

    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print("ASU baseline (A1)")
    print(f"  frozen_spec_hash: {FROZEN_SPEC_HASH}")
    print(f"  python_version:   {platform.python_version()}")
    for seed in SEEDS:
        result = per_seed[str(seed)]
        print(f"  seed {seed}:")
        print(f"    digest:               {result['digest']}")
        print(f"    decisions:            {result['decisions']}")
        print(f"    steps:                {result['steps']}")
        print(f"    seconds:              {result['seconds']:.6f}")
        print(f"    seconds_per_decision: {result['seconds_per_decision']:.6f}")
    print(f"  aggregate seconds_per_decision: {aggregate_seconds_per_decision:.6f}")
    print(f"  wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
