"""
asu_profile.py
---------------
Phase step A2: profile the same scenario as A1 (seed 3, first 300 engine
steps) under cProfile, to find hotspots ahead of any future optimisation
work. This script performs NO optimisation and NO changes to
ASU_FROZEN_TEACHER/ or monopoly_game_engine/ — it is pure measurement
tooling.

Writes artifacts/asu_profile_before.txt with:
  - a header line: total decisions, total profiled seconds
  - top 25 functions by cumulative time
  - top 25 functions by tottime (self time)

Usage:
    .venv/bin/python tools/asu_profile.py
"""

from __future__ import annotations

import cProfile
import io
import pstats
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ASU_FROZEN_TEACHER.core import ASUValueV1  # noqa: E402
from ASU_FROZEN_TEACHER.evaluate import (  # noqa: E402
    _ScriptedAdapter,
    _new_seeded_game,
)
from monopoly_game_engine.agents_fixed import FP_AGENT_CLASSES  # noqa: E402

SEED = 3
MAX_STEPS = 300
ARTIFACTS_DIR = ROOT / "artifacts"
OUTPUT_PATH = ARTIFACTS_DIR / "asu_profile_before.txt"


def run_scenario() -> int:
    """Run the seed-3, 300-step scenario; return the number of seat-0 decisions."""
    game = _new_seeded_game(SEED)
    env = game.env

    seat0 = ASUValueV1(0)
    opponents = {
        1: _ScriptedAdapter(FP_AGENT_CLASSES[0](1), 1),  # TheHoarder
        2: _ScriptedAdapter(FP_AGENT_CLASSES[1](2), 2),  # TheDealMaker
        3: _ScriptedAdapter(FP_AGENT_CLASSES[2](3), 3),  # TheGambler
    }

    decisions = 0
    steps = 0
    while steps < MAX_STEPS and not env.done:
        actor = env.whose_turn()
        if actor == 0:
            decision = seat0.decide(env)
            decisions += 1
            action = decision.selected_action
        else:
            action = opponents[actor].choose_action(env)
        game.step(action)
        steps += 1

    return decisions


def main() -> None:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    profiler = cProfile.Profile()
    started = time.perf_counter()
    profiler.enable()
    decisions = run_scenario()
    profiler.disable()
    total_seconds = time.perf_counter() - started

    cumulative_buffer = io.StringIO()
    pstats.Stats(profiler, stream=cumulative_buffer).sort_stats(
        "cumulative"
    ).print_stats(25)

    tottime_buffer = io.StringIO()
    pstats.Stats(profiler, stream=tottime_buffer).sort_stats("tottime").print_stats(25)

    header = (
        f"asu_profile_before.txt -- seed={SEED} max_steps={MAX_STEPS}\n"
        f"total decisions: {decisions}\n"
        f"total profiled seconds: {total_seconds:.6f}\n"
    )

    body = (
        header
        + "\n"
        + "=" * 79
        + "\nTop 25 by cumulative time\n"
        + "=" * 79
        + "\n"
        + cumulative_buffer.getvalue()
        + "\n"
        + "=" * 79
        + "\nTop 25 by tottime (self time)\n"
        + "=" * 79
        + "\n"
        + tottime_buffer.getvalue()
    )

    OUTPUT_PATH.write_text(body)

    print(header)
    print(f"wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
