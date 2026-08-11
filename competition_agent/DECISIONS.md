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

**Correction to the per-decision figures above.** The 0.0015 s/decision value
figure was measured on early-game states of seed 3 and does not generalise: a
full 1200-step game of seed 1 costs 25.6 s for 258 seat-0 decisions, i.e.
**~0.10 s/decision** averaged over a developing board. Decision cost grows
with board development (more legal actions, richer monopoly planning). The
0.69 s/move rollout figure is likewise an early-game number and should be
treated as a lower bound. Phase 4's timing budget must be measured on
late-game states, not early ones.

## D0.7 — Opacity discipline reconsidered and reaffirmed

D0.3 was revisited deliberately rather than by inertia, because relaxing it
would cut Phase 1 from roughly two days to one: `decide()` returns per-action
value components, both safety margins, trade gains, auction ceilings and
rejection reasons, and the package exports `evaluate_value`,
`rent_projection`, `safety_breakdown` and `monopoly_value` directly.

**Reaffirmed unchanged.** Probes record the selected action id and nothing
else. The reasoning:

1. The brief's framing — "treat the teacher as an opaque function
   `decide(env) -> action`", "the evidentiary chain must rest on observed
   behaviour alone" — is explicit, and the competition legitimacy argument
   rests on it. A spec transcribed from returned internals would not
   demonstrate that the policy was derived from behaviour.
2. It has already proved productive rather than merely restrictive. A2–A5
   recovered the exact gate structure *and* its rent-projection term from
   flip points alone, to the dollar, including the doubles tail. Nothing was
   lost by not reading the breakdown.
3. The constraint is enforced by construction, not discipline:
   `competition_agent/policies.py` and `probe_harness.py` import only
   `ASUValueV1`, `ASURolloutV1` and the seeded-game helpers. Adding a
   breakdown-reading import would be a visible diff, not a silent slip.

This decision should not be revisited again without a stated reason recorded
here. If it ever is relaxed, every rule in `SPEC.md` derived after that point
must be tagged as internals-derived so the audit trail stays honest about
which rules are behavioural evidence and which are transcription.

## D0.8 — The 200-game reference run was killed; `bench.py` needs checkpointing

The Phase 0 rollout reference (200 games, `rollout,fixed-a,fixed-b,fixed-c`)
ran for **2h09** and was then killed to free the CPU for the audit-trail
certification, which gates all further probing. The certification is a hard
prerequisite for Phase 1 validity; the reference number is not, so the
reference lost the tie.

Two hours of compute were lost because `bench.py` accumulates results in
`pool.map` and writes JSON only at the end — a run that is interrupted
produces nothing at all. That is a design flaw for jobs of this length.

**Decision:** before the reference run is restarted, `bench.py` must stream
per-game records to disk as they complete (`imap_unordered` + append) and
support resuming by skipping seeds already present in the output file. Long
benchmarks are then interruptible at no cost, and the Phase 4/5 head-to-head
runs (≥300 and ≥500 games) inherit the same property.

## D1.1 — Phase 4 gate: RESOLVED, and the layer is rescoped to two families

The conditional gate was stated as: *Phase 4 is built only if the
adversarial-state divergence rate is statistically distinguishable from zero;
if divergence is negligible even on constructed states, Phase 4 is skipped and
its time moves to Phase 5.*

**Gate outcome: PASSED — Phase 4 proceeds.** Over 230 constructed boundary
states the rollout changed the decision in 81 cases, a rate of **35.2%**
(95% Wilson CI [29.3%, 41.6%]). Both policies are deterministic given a state,
so the null "rollout never changes the decision" is not merely rejected at some
confidence level — a single divergence falsifies it outright, and there are 81.

**But the flat reading of the gate would have produced the wrong design.**
Divergence is not spread evenly; it is almost entirely confined to two action
families:

| family | divergence | cost ratio |
| --- | --- | --- |
| auction | 94.6% | 1035× |
| build | 58.3% | 464× |
| buy | 0.0% | 112× |
| trade | 0.0% | 309× |

Wrapping *every* decision in rollout — the Phase 4 brief's default reading —
would spend 112× on buy decisions and 309× on trade decisions to reproduce an
answer the fast path already gives, in 126 of 126 cases tested.

**Decision.** The Phase 4 rollout layer is applied **selectively**, gated on
action family: auctions and build/improve decisions get lookahead; buy and
trade decisions take the hybrid's answer directly. The K/M/P budget is then
spent where it demonstrably changes outcomes, which also relieves the
per-move time limit — the expensive path runs on a minority of decisions.

This gate is re-checked, not assumed, once the clone exists: the divergence
measurement above is between the *teacher's* two variants, and the clone's
own value/rollout divergence profile could differ. `p08_rollout_divergence.py`
is written to re-run against any policy pair.

**Caveat on coverage.** The 0% buy/trade divergence is measured over 112 buy
and 14 trade boundary states. The trade sample is small; before buy/trade are
finally excluded from the rollout path, the trade-boundary population needs
widening (Experiment 6 will produce it). Until then the exclusion is provisional
and is recorded here so it is not mistaken for a settled result.

## D1.2 — Two teacher weaknesses found in Phase 1, carried to Phase 5

Recorded now so Phase 5 modules are aimed at measured gaps rather than
assumed ones.

1. **Rent projection is already sharp on the collection side** (A3–A6). The
   teacher enumerates 2d6 complete-turn landings over opponents' *actual*
   positions, including doubles-driven extra rolls, and prices deeds
   accordingly. Phase 5 module 1 should therefore target rent *paid to*
   opponents from their developed holdings, not rebuild the collection side.

2. **The auction ceiling ignores group presence it does not already have**
   (B3, B5). The teacher pays the same for the first deed of a colour group as
   for the second, and escalates only on the completing deed. An opponent can
   take the first two deeds of a group at ordinary prices and only meets
   resistance on the third — by which point it holds the blocking position.
   This is a direct opening for Phase 5 module 2 (denial-value trading), and
   it is a weakness in the *teacher we are cloning*, so the clone will inherit
   it unless the module explicitly overrides the auction ceiling.

## D1.3 — Phase 4 gate CORRECTED: trade goes back into the rollout path

D1.1 scoped the Phase 4 rollout layer to auction and build only, excluding buy
and trade on the strength of p08's 0% divergence in both. That exclusion was
recorded as **provisional for trade**, because the trade sample was 14 states
from a single narrow setup. The caveat was justified.

Experiment 6 built the real trade surface — seat 0 holding four deeds against
a rival holding five, sweeping the sweetener across the whole accept region —
and measured **50 divergences in 54 states, 92.6%**. Trade is not a family
where lookahead is redundant; it is the family where the two variants agree
*least*.

| family | p08 (narrow) | p06 (wide) | in rollout path? |
| --- | --- | --- | --- |
| auction | 94.6% (56) | — | yes |
| build | 58.3% (48) | — | yes |
| **trade** | **0.0% (14)** | **92.6% (54)** | **yes — corrected** |
| buy | 0.0% (112) | — | no (112 states, one setup) |

**Decision.** The selective rollout path covers **auction, build and trade**.
Buy remains on the fast path, but that exclusion now carries the same warning
the trade one did: 112 states is a decent sample, yet they came from a single
board configuration, and the trade case is a worked example of how badly a
one-setup sample can mislead. Before the competition entry is frozen, buy must
be re-tested on a population that varies board configuration, not just cash.

**Process lesson, recorded because it nearly shipped a wrong design.** A 0%
result on a narrow population is not evidence of absence; it is evidence about
that population. Divergence probes must vary the *board*, not only the
parameter under sweep. Both p08's trade cell and its buy cell hold board shape
fixed, which is exactly the flaw that produced the wrong conclusion.

## D1.4 — Orphaned workers: the bug that silently halved throughput for 3.5 hours

**Symptom.** After the 200-game reference run was stopped (D0.8), everything
was inexplicably slow: the teacher certification timed out twice at 10 minutes
on an apparently idle box, a full value game measured 25.6 s against an
expected ~3 s, and Experiment 6 took over half an hour.

**Cause.** The run was stopped with `pkill -f "bench.py --games 200"`. That
pattern matches the parent only. `multiprocessing` workers are spawned with a
command line of `python -c from multiprocessing.spawn import spawn_main...`,
which contains neither the script name nor its arguments, so the ten workers
never matched, were re-parented to init, and kept running. They were found
still alive **3.5 hours later** at ~55% CPU each — 911% of the machine's
1000% total — computing results that no living process would ever collect.

Two independent defects made this possible:

1. SIGTERM to the parent kills it immediately, so `with mp.Pool(...)` never
   reaches its cleanup and the children survive.
2. Even a correct pattern kill cannot match a worker's command line, so there
   was no way to clean up after the fact except by hand.

**Fix.** `competition_agent/proc.py`:

- `managed_pool(workers)` installs SIGTERM/SIGINT/SIGHUP handlers that call
  `pool.terminate()` before re-raising, and puts the parent in its own process
  group so the job can be killed as a unit. Wired into `bench.py`,
  `certify_teacher.py`, and all seven pooled probes.
- `kill_by_script(name)` resolves script → pid → process group → group kill,
  which is what a bare `pkill -f` cannot do.
- `find_orphans()` / `python3 -m competition_agent.proc orphans` lists python
  workers whose parent is init, so this smell is diagnosable in seconds rather
  than mistaken for a slow machine.

Verified: a pool running a real module-level target is SIGTERMed, and both the
child count and the count of processes matching the script drop to zero. The
first version of that test was invalid — the workers died unpickling the
target rather than running it, so it would have passed against a broken
implementation — and was rewritten against a real module file.

**What it cost.** Every timing figure taken between the kill and the cleanup
is contaminated and none should be trusted: the 25.6 s/game measurement in
D0.6, the certification's two timeouts, and Experiment 6's runtime. The
*decision* data from those runs is unaffected — the teacher is deterministic
given a state, so contention changes only wall-clock, not selected actions.
Timing-sensitive conclusions (Phase 4's per-move budget) must be re-measured
on a quiet machine.
