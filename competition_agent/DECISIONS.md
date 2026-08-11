# DECISIONS.md

Engineering choices and rationale for the competition agent. Newest phase last.

---

## D0.1 — Repository facts: what was verified, and what was wrong

The brief supplied a list of "verified, do not rediscover" repository facts.
Before building anything I re-verified them, because a wrong premise here would
invalidate every later phase. Result:

**Confirmed by direct measurement** (`competition_agent/probes/` and runtime
introspection, no source reading of the teacher):

| Claim | Status |
| --- | --- |
| 300-dim observation from `env._get_state(pid)` | confirmed — `len(...) == 300` |
| 2958-dim action space | confirmed — `actions.ACTION_SPACE_SIZE == 2958` |
| `OFFSETS` table with the named families | confirmed — 12 families, `binary`..`auction` |
| phases `pre_roll / post_roll / out_of_turn / auction` | confirmed |
| `env.get_allowed_actions(pid)`, `env.step`, `env.whose_turn()` | confirmed |
| auction state fields (all five) | confirmed present on `MonopolyEnv` |
| `ASUValueV1` / `ASURolloutV1` with `decide` + `choose_action` | confirmed |
| teacher is deterministic given the same state | confirmed — see D0.2 |

**Contradicted.** None of the six claimed "existing starting points" exist
anywhere in the repository:

    probe_teacher.py   distill_collect.py   distill_train.py
    student_policy.py  student_policy.pt    heuristic_policy.py

A `find` across the whole tree returns nothing for any of them. The brief
budgets Phase 1 as "extend `probe_teacher.py`" and Phase 3 as "retrain the
existing ~82%-agreement student", so both phases start from zero rather than
from a working artifact. This is recorded here rather than silently absorbed
because it changes the effort estimate for those two phases, not the plan.

**Partial substitutes that do exist and are being reused instead of rewritten:**

- `ASU_FROZEN_TEACHER/evaluate.py` — a seat-balanced paired-block evaluator
  exposing `_new_seeded_game(seed)` and `_ScriptedAdapter`. Used (imported, not
  read) so `bench.py` seeds games identically to the existing artifacts.
- `tools/asu_baseline.py` — a measurement-only ASU driver that establishes the
  digest/timing convention followed here.
- `tests/test_asu_phase_a.py` — 24 passing tests pinning teacher behaviour.

## D0.2 — The teacher is modified but behaviourally frozen; probing is safe

`git status` shows `ASU_FROZEN_TEACHER/core.py` with **258 added / 32 removed
uncommitted lines**. A modified teacher would undermine the whole premise of
the exercise: probe results would characterise a local variant, and the audit
trail would not describe the policy the organizer froze.

It does not, and the evidence is already in the repository. `artifacts/`
contains a pre-modification digest (`asu_baseline_locked.json`) and the current
one (`asu_baseline.json`). Every seat-0 `decide()` result is canonicalised and
SHA-256 chained per seed:

| seed | locked digest | current digest | match |
| --- | --- | --- | --- |
| 3  | `65a666333635d9f8…` | `65a666333635d9f8…` | yes |
| 7  | `deba3445cdd4eb9f…` | `deba3445cdd4eb9f…` | yes |
| 11 | `144b23efba152c4d…` | `144b23efba152c4d…` | yes |

All 24 tests in `tests/test_asu_phase_a.py` pass. The change is a
behaviour-preserving optimisation: aggregate cost fell from **0.0501 s** to
**0.0167 s** per decision (3.0×). The decision *function* is bit-identical on
every probed state, so behavioural reverse engineering targets the intended
policy.

**Decision:** probe the working tree as-is. Re-run `tools/asu_baseline.py` and
compare against `asu_baseline_locked.json` before each phase's probe batch;
a digest change invalidates that batch.

## D0.3 — `decide()` returns internals; we use only the selected action

`ASUValueV1.decide(env)` returns a `Decision` carrying, for *every* legal
action, all four value components, both safety margins, trade gains, auction
ceilings, and rejection reasons. `ASU_FROZEN_TEACHER` additionally exports
`evaluate_value`, `rent_projection`, `safety_breakdown`, `monopoly_value` and
friends as public API.

Using any of that would reduce Phase 1 from inference to transcription. It is
technically "observed behaviour" — no source is read — but it is reading the
teacher's internals through a window, and a spec derived that way would not be
the artifact the brief asks for.

**Decision:** the teacher is consumed strictly as `decide(env) -> action`.
Probes record the *selected action id only*. Value components, safety
breakdowns and rejection reasons are never read, and no `ASU_FROZEN_TEACHER`
helper other than the two policy classes is called from probe or policy code.
`competition_agent/policies.py` enforces this by construction: it imports only
`ASUValueV1`, `ASURolloutV1`, and the harness helpers.

This is the strict reading of "treat the teacher as an opaque function". If it
is ever relaxed, Phase 1 collapses to roughly a day — but the audit trail then
proves much less.

## D0.4 — Reading policy for allowed documents

`ASU_FROZEN_TEACHER/README.md` and `spec.py` are explicitly permitted reading
and both were read. They are rich: the README states the value decomposition
`V = M_assets + R_short + R_long + M_monopoly`, the 5-turn/5-lap horizons, the
`2 ** missing_deeds` monopoly discount, both safety gate inequalities, the trade
gain thresholds, and the auction ceiling rule; `spec.py` adds the numeric
constants (`minimum_cash: 200`, `terminal_utility: 1_000_000`, rollout
`8 x 8 x 32`, seed 0).

**Decision:** these are treated as *hypothesis sources*, never as evidence.
Every rule in `SPEC.md` must still cite a probe CSV that confirms it on
observed decisions, and a documented rule that probes contradict is recorded as
contradicted. Reading them makes Phase 1 efficient — it tells us which
experiments to run — but the evidentiary chain stays behavioural, which is what
makes the derived policy defensible.

`core.py` and `evaluate.py` have not been opened. `git diff` on `core.py` was
deliberately not run (`--stat` only, which reports line counts and no source).

## D0.5 — `bench.py` design

- **Seeding.** Game *k* uses `--seed + k` via `_new_seeded_game`, matching the
  existing artifacts. Stochastic policies are seeded from `(game_seed, seat)`.
  Every seed is written to the output JSON.
- **Two win rates, not one.** The engine terminates a game either by
  elimination (one solvent player) or by hitting its round cap; `--max-steps`
  adds a harness-level cap. `env.winner()` falls back to the net-worth leader
  when no one has been eliminated, so counting it as a "win" silently conflates
  two different outcomes. `bench.py` reports **leader rate** (all games) and
  **decisive rate** (elimination games only) side by side, following the
  convention the repo's own evaluator uses with `provisional_leader`. Wilson
  95% intervals on both — Wilson rather than normal-approximation because the
  per-seat counts are small and rates land near 0 and 1.
- **Scripted-agent fallback.** The fixed agents sometimes return `END_TURN`
  where only liquidation is legal. `bench.py` routes them through the repo's
  `_ScriptedAdapter` so the identical compatibility fallback applies; ASU and
  learned policies stay strictly checked and any illegal action raises.
- **Parallelism.** `--workers` uses a process pool over whole games. Games are
  independent and each is seeded from its own seed, so results are invariant to
  worker count.

## D0.6 — Measured costs, and what they imply for Phase 4

Warm per-decision cost on this machine (10 cores):

| policy | seconds / decision |
| --- | --- |
| `ASUValueV1` | 0.0015 (warm) / 0.0167 (aggregate incl. cold caches) |
| `ASURolloutV1` | 0.69 |

The rollout variant is ~460× the value variant, not the ~2048× a naive
`8 x 8 x 32` reading predicts, so it is memoising heavily across candidates.
Two consequences:

1. A 200-game rollout reference run is ~3 CPU-hours — feasible parallelised,
   which is why the reference number is being measured rather than estimated.
2. Phase 4's K/M/P budget has real headroom, but 0.69 s/move is the number to
   beat, and it must be re-measured on competition hardware rather than
   inherited from here.

Early incidental observation, not yet a probe: over the first 10 seat-0
decisions of seed 3, `ASURolloutV1` and `ASUValueV1` selected the **same
action 10/10 times**. If lookahead only rarely changes the choice, Phase 1
experiment 8 (rollout divergence) needs states chosen adversarially rather
than sampled from early play. Recorded here so Phase 1 designs for it.
