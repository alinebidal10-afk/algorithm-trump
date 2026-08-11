"""Harvest trade-proposal decisions from real teacher-driven play.

Why not a wider synthetic generator
-----------------------------------
D2.7 records four separate occasions where a synthetic sample produced a
confident wrong conclusion, the last with 402 states and tight intervals. The
problem was never sample size; it was that generated boards are not the boards
real play produces. Widening the generator to ~500 proposal boards would buy
statistical power over the wrong distribution.

So this collects the same decisions from actual games: the teacher drives,
and every state where at least two `exch_trade` actions are legal is recorded
along with the full candidate set and what the teacher actually did. That is
simultaneously the ranking data (which candidate, when it proposes) and the
gate data (whether it proposes at all), drawn from the distribution the policy
will be judged on.

Split discipline: by **game seed**, not by decision. Decisions within one game
share a board and are heavily correlated, so a decision-level split would leak
and inflate held-out accuracy.

Output: probes/trade_harvest.jsonl  (one record per decision)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
           "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_v, "1")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ASU_FROZEN_TEACHER import ASUValueV1  # noqa: E402
from ASU_FROZEN_TEACHER.evaluate import _ScriptedAdapter, _new_seeded_game  # noqa: E402
from monopoly_game_engine.actions import OFFSETS  # noqa: E402
from monopoly_game_engine.agents_fixed import FP_AGENT_CLASSES  # noqa: E402
from monopoly_game_engine.constants import COLOR_GROUPS, PROPERTIES, PROPERTY_IDS  # noqa: E402

from competition_agent.proc import managed_pool  # noqa: E402
from competition_agent.spec_model import (  # noqa: E402
    SHORT_TURNS, multi_turn_landings, rent_for,
)

OUT = Path(__file__).resolve().parent / "probes" / "trade_harvest.jsonl"
N = len(PROPERTY_IDS)


def decode(action, others):
    loc = action - OFFSETS["exch_trade"]
    p = loc // (N * (N - 1))
    rem = loc % (N * (N - 1))
    off = rem // (N - 1)
    rr = rem % (N - 1)
    req = rr if rr < off else rr + 1
    if p >= len(others):
        return None
    return others[p], PROPERTY_IDS[off], PROPERTY_IDS[req]


def deed_facts(env, pid, sq):
    """Raw, model-free quantities. No valuation is baked in here, so the
    analysis can test hypotheses this file does not presuppose."""
    prop = env.properties[sq]
    color = PROPERTIES[sq]["color"]
    group = COLOR_GROUPS[color]
    owner = prop.owner

    saved = prop.owner
    prop.owner = pid
    try:
        rent_if_ours = 0.0
        for opp in env.players:
            if opp.player_id == pid or opp.bankrupt:
                continue
            for land, p in multi_turn_landings(opp.position, SHORT_TURNS):
                if land == sq:
                    rent_if_ours += p * rent_for(env, sq)
    finally:
        prop.owner = saved

    return {
        "sq": sq,
        "price": PROPERTIES[sq]["price"],
        "base_rent": PROPERTIES[sq]["rent"][0],
        "color": color,
        "group_size": len(group),
        "ours_in_group": sum(1 for s in group
                             if env.properties[s].owner == pid),
        "theirs_in_group": sum(1 for s in group
                               if env.properties[s].owner not in (None, pid)),
        "owner": -1 if owner is None else owner,
        "mortgaged": bool(prop.mortgaged),
        "houses": prop.houses,
        "rent_if_ours": rent_if_ours,
        "is_monopoly": bool(prop.is_monopoly),
    }


def _play(seed_maxsteps):
    seed, max_steps = seed_maxsteps
    game = _new_seeded_game(seed)
    env = game.env
    teacher = ASUValueV1(0)
    opp = {i: _ScriptedAdapter(FP_AGENT_CLASSES[i - 1](i), i) for i in (1, 2, 3)}
    others = [1, 2, 3]
    out, steps = [], 0

    while steps < max_steps and not env.done:
        actor = env.whose_turn()
        if actor == 0:
            legal = [int(a) for a in env.get_allowed_actions(0)]
            cands = [a for a in legal
                     if OFFSETS["exch_trade"] <= a < OFFSETS["auction"]]
            chosen = int(teacher.choose_action(env))
            if len(cands) >= 2:
                facts = {}

                def f(sq):
                    if sq not in facts:
                        facts[sq] = deed_facts(env, 0, sq)
                    return facts[sq]

                rows = []
                for a in cands:
                    d = decode(a, others)
                    if d is None:
                        continue
                    tgt, off, req = d
                    rows.append({"a": a, "tgt": tgt,
                                 "off": f(off), "req": f(req)})
                if rows:
                    out.append({
                        "seed": seed, "step": steps,
                        "phase": env.phase,
                        "round": int(getattr(env, "round", -1)),
                        "our_cash": env.players[0].cash,
                        "our_deeds": len(env.players[0].properties),
                        "chosen": chosen,
                        "proposed": chosen in cands,
                        "n_cands": len(rows),
                        "cands": rows,
                    })
            action = chosen
        else:
            action = int(opp[actor].choose_action(env))
        game.step(action)
        steps += 1
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=60)
    ap.add_argument("--seed-base", type=int, default=910000)
    ap.add_argument("--max-steps", type=int, default=1200)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    jobs = [(args.seed_base + k, args.max_steps) for k in range(args.seeds)]
    with managed_pool(args.workers) as pool:
        batches = pool.map(_play, jobs)

    recs = [r for b in batches for r in b]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")

    prop = sum(1 for r in recs if r["proposed"])
    cands = sum(r["n_cands"] for r in recs)
    seeds = len({r["seed"] for r in recs})
    print(f"decision states with >=2 exchange candidates : {len(recs)}")
    print(f"  of which the teacher proposed             : {prop} "
          f"({100*prop/max(len(recs),1):.1f}%)")
    print(f"  total candidates                          : {cands}")
    print(f"  distinct game seeds                       : {seeds}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
