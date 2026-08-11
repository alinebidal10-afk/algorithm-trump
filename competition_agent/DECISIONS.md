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

## D2.1 — Phase 2 status: 76.4% held-out, blocked on trade proposal

`spec_policy.py` is a priority-ordered rule pipeline; every branch cites the
SPEC rule it implements. `spec_model.py` rebuilds the quantities the rules are
stated in — the 2d6 complete-turn landing enumeration (A4/A5), rent flow from
real positions (A6), liquidatable worth (D3/F3), and both safety gates (D1–D4).

**Model validation before policy work.** `gates_ok` was checked against the
probe corpus first: it reproduces **28/28** measured buy flip points within $2
(26 exact) and every gate-1 row of the build and unmortgage sweeps exactly.
Gate 2 carries a known residual, recorded in the function's docstring rather
than curve-fitted away — the clone is $21–$81 more cautious than the teacher
when opponents are heavily developed, a safe direction to err.

**Agreement (held-out, seeds 900000+, disjoint from all probe seeds):**

| family | n | rate |
| --- | --- | --- |
| ROLL_DICE | 212 | 100.0% |
| unmortgage | 11 | 100.0% |
| BUY_PROPERTY | 26 | 96.2% |
| END_TURN | 931 | 98.2% |
| auction | 153 | 90.8% |
| DECLINE_TRADE | 315 | 69.5% |
| improve_house | 37 | 27.0% |
| **exch_trade** | **281** | **0–5%** |
| buy_trade / sell_trade / mortgage | 36 | 0% |
| **TOTAL** | **2005** | **76.4%** |

Against the ≥90% target: **FAIL**. The decision families the probes covered
directly are in good shape — buy, auction, jail, roll, unmortgage all sit at
90–100%. The gap is concentrated in trade *proposal*.

**Root cause: an experiment that was never briefed.** Phase 1 mapped the trade
accept/decline surface (Experiment 6) — the reply side. It never asked what
the teacher *proposes*. That family is ~15% of all decisions (307 of 474
disagreements), so no amount of tuning the covered rules reaches 90%.

**Three attempts, all recorded because the failures are informative:**

1. *No proposal rule* — 76.4%. The clone simply ends its turn.
2. *Completion heuristic* (p09: offer the least valuable spare for the deed
   completing a group) — **75.0%**, `exch_trade` 5%. p09's narrow setup made
   this look right: 36/36 proposals there were exactly that shape. Held-out
   play refuted it — across 281 real proposals the teacher requested 23, 25,
   37, 12, 9, 31, 27, 35 and *offered valuable* deeds (13, 24, 9, 21), not
   spares. Agreement on the requested deed alone was 27/189.
3. *General two-sided +EV search* over all legal exchange pairs, scored with
   the same deed valuation used elsewhere — **73.8%**, `exch_trade` 0.4%.

Attempt 3 is structurally the right shape and still scored worst, which
locates the problem precisely: **`deed_value` is not accurate enough to rank
exchange pairs.**

> **RETRACTED (see D2.6).** This paragraph originally read "calibrated well
> enough for threshold decisions — where only its comparison against a cash
> gate matters, hence 96% on buy and 91% on auction". The buy half is wrong:
> `_buy` never calls `deed_value`. It is `gates_ok(env, pid, price)` and
> nothing else, so buy's agreement is evidence about the safety gates and says
> nothing about the valuation, in either direction. The auction half stands as
> a fact but not as support for "calibrated well enough" — D2.6 shows removing
> the monopoly term *improves* auction by 5.0 points and shrinking it by 8.2.
> The valuation is not well calibrated for thresholds either; it is merely
> outvoted there by price and rent.

**Next step, and it is a probe, not a tuning pass.** Attempts 2 and 3 were both
made without evidence to guide them, which is why each was worse than the last.
Experiment 9b must measure the teacher's *ranking* directly: fix a board, offer
a forced choice between two specific exchanges, and sweep the pair to recover
the ordering deed-by-deed. That calibrates `deed_value` on relative
comparisons instead of inferring it from thresholds. Until that exists, no
further change should be made to `_propose_trade`.

Secondary, smaller gaps once trade is solved: `improve_house` at 27% (E1's
rent ordering is right in isolation but something else outranks it in real
positions), and `DECLINE_TRADE` at 69.5% (the clone accepts offers the teacher
refuses — consistent with the same valuation weakness).

## D2.2 — Experiment 9b: ranking calibration data, and why board diversity was mandatory

The Phase 2 gap is trade, and the fault was located in `deed_value`: accurate
enough for thresholds (buy 98.4% — RETRACTED, see D2.6: `_buy` does not call
`deed_value`; auction 90.5%) but not for ranking two deeds
against each other (`exch_trade` 0.3% over 722 held-out decisions).

**Board diversity was made a design requirement of this probe, not an
afterthought.** Two narrow samples had already produced confident, wrong
conclusions: p08's 14-state trade cell reported 0% rollout divergence against
Experiment 6's 92.6% (D1.3), and p09's single board shape showed 36/36
proposals were "cheapest spare for the completing deed" — a rule that scored
5% in real play. Both looked unambiguous at the time.

p09b therefore samples 400 boards from a seeded generator randomising deed
allocation (seat 0, one rival, and a third party so the board is not
two-sided), all four positions, development level, bank house/hotel stock,
mortgage flags and every player's cash. Diversity is **reported rather than
claimed**: the sample covers 2–5 deeds a side, 0–4 development levels, 4 bank
stock levels, 7 cash levels, 23 distinct candidate-set sizes, and **all ten
colour groups on both the offered and the requested side**.

### Result: two separate defects, not one

| | |
| --- | --- |
| boards offering a real ranking choice | 400 |
| teacher proposed a trade | **118 (29.5%)** |
| teacher ended its turn instead | **282 (70.5%)** |
| our model's top-1 accuracy | **13/118 = 11.0%** |
| teacher's pick inside our top-3 | 21.2% |
| teacher's pick inside our top-5 | 32.2% |
| teacher's pick inside our top-10 | 62.7% |
| median rank our model gives its pick | 8 (mean 10.4, worst 40) |

**Defect 1 — when to propose.** The teacher proposes on fewer than a third of
boards where a legal exchange exists. `_propose_trade` fires whenever any pair
scores positive, which is most of the time. That is the source of the 200
`END_TURN` disagreements: the same fault, counted in a different row. Whatever
gate suppresses 70% of proposals is not modelled at all, and none of the
obvious board features separate the two populations — deeds held, cash,
candidate count and development are nearly identical across proposed and
ended-turn boards (3.64 vs 3.48 deeds, $1,170 vs $1,153, dev 0.05 vs 0.13).
The gate is therefore a property of the *offers available*, not of the board,
which points at a threshold on the gain itself.

**Defect 2 — which to propose.** Top-1 of 11% against a candidate set
averaging 22 is only modestly better than the 4.5% a random pick would give,
and top-10 at 62.7% says the correct action is usually somewhere in the upper
half of our ordering but rarely at the top. The ordering carries signal; it is
not calibrated.

The direction is at least sane: the teacher asks for more than it gives (mean
requested price $224 vs offered $204; requested price exceeds offered in
70/118), and it trades across all ten colours rather than favouring any.

### Next work item

Fit `deed_value` against `p09b_trade_ranking.csv` as a ranking problem —
top-1 accuracy on the 118 proposal boards is the objective, with the 282
end-turn boards as the negative class for the propose/don't-propose gate.
Both defects are measurable on this one file, so the fit can be validated
without touching held-out play, and held-out agreement stays an honest test.

No further change to `_propose_trade` until that fit exists. The two previous
attempts were both made without calibration data and both regressed.

## D2.3 — Debt/jail evaluation set: G1 refuted, and rule interaction exposed

`p10_debt_jail_eval.py` builds the population ordinary play never reaches —
250 randomised debt boards (followed through the whole liquidation chain) and
250 randomised jail boards, each swept in both phases. 1,508 decisions.

| scenario | agree | n | rate |
| --- | --- | --- | --- |
| debt | 833 | 1040 | **80.1%** |
| jail_post_roll | 157 | 218 | **72.0%** |
| jail_pre_roll | 106 | 250 | 42.4% |

Per family: `mortgage` 83.8% (980), `USE_GOOJ_CARD` 100% (53), `PAY_BAIL`
78.6%, `sell_house` 33.3%, `ROLL_DICE` 61.6%.

**F1–F5 and G2–G5 largely survive contact.** Liquidation at 80% and the jail
exit choice at 72% are the first real validation these families have had;
`USE_GOOJ_CARD` is perfect across 53 states. `sell_house` at 33% is a genuine
ordering defect within F4.

**G1 is refuted.** It was stated as "in pre_roll the teacher defers, choosing
END_TURN" on the strength of p07's 224/224. This set shows that was p07's
*setup*, not the rule: over 250 jailed pre_roll states the teacher chose
END_TURN in only 106 and spent the rest unmortgaging (63) and proposing
trades (95). Being in jail suppresses the exit decision, not every other rule.
Recorded in SPEC as a contradiction, third one on the record.

**Fixing G1 made the score worse, and that is the finding.** Letting the
pipeline fall through dropped jail_pre_roll from 42.4% to 23.2% and the total
from 72.7% to 69.5%, because the rules that now fire — trade proposal at 4%,
unmortgage at 14% — are worse than doing nothing. G1's wrong rule was
accidentally protective.

The fix is kept anyway. Reverting would be tuning to a symptom: the pipeline
would score better while containing a rule known to be false, and the debt
figures would still be carried by `mortgage` alone. It does mean **the trade
gate is a blocker, not an optimisation** — several families are held hostage
to it.

## D2.4 — Both trade fits FAIL, and they fail informatively

`fit_trade.py`, split 60/40 by board, fixed before any search (240 train / 160
held-out; 71 / 47 proposals).

**Defect 2 — ranking.** 4,000 weight searches over
(price, rent, mono, mortgaged) differences found **nothing better than the
baseline**: train top-1 stayed 12.7%, held-out 8.5%. The optimum is the
starting point.

**Defect 1 — gate.** The best threshold scores 70.4% on train — *exactly* the
never-propose baseline — and 70.6% held out. The fitted gate degenerates to
"never propose anything".

**Interpretation: the feature set is wrong, not the weights.** A search that
cannot beat its own initialisation, and a threshold that collapses to a
constant classifier, both say the same thing: these four features contain no
signal about which exchange the teacher picks or whether it proposes at all.
More search, more features of the same kind, or a smarter optimiser would all
be wasted.

**The likely omission is that every feature is one-sided.** They score the
trade from our perspective only. The published description of the teacher
requires proposer gain > 0, **recipient gain >= 0**, and *both* parties'
safety gates — and Experiment 6 already demonstrated the recipient side
behaviourally (H2: the accept region's upper edge is set by the
counterparty's ability to pay, not by our valuation). If most high-gain-for-us
candidates are infeasible for the recipient, the teacher's pick is the best
*feasible* one, which a one-sided ranking cannot reproduce at any weighting.

**Next step:** re-extract features with the recipient's valuation and both
safety gates included, then re-fit on the same fixed split. If a two-sided
feasibility filter alone lifts top-1 substantially, that confirms the
diagnosis before any weight tuning. The split and the held-out play set both
stay untouched so the check remains honest.

**Phase 2 stays open.** Neither defect is closed, `sell_house` ordering is a
known F4 defect, and G1's correction is net-negative until the gate lands.

## D2.5 — Three diagnoses, three refutations, and what they jointly imply

The trade-ranking failure has now survived three separate explanations. Each
was tested in isolation before anything was built on it, and each was refuted
by its own test rather than by a later regression.

| # | diagnosis | test | outcome |
| --- | --- | --- | --- |
| 1 | weights are miscalibrated | 4,000-iteration search on train | **refuted** — nothing beat the initialisation; train top-1 stayed 12.7% |
| 2 | features are one-sided | feasibility filter alone, no tuning | **refuted** — top-1 fell (12.7%→10.1%), and the filter discarded the teacher's own pick in 60/118 cases |
| 3 | marginals are non-separable | joint `state_value` swap delta vs difference of marginals | **refuted** — scores change by up to 23× relative, argmax identical on 40/40 boards |

Refutation 3 is the informative one. Replacing a difference of marginals with a
genuine whole-position valuation moved candidate scores by more than an order
of magnitude and **changed which candidate ranked first exactly zero times**.
That is not a small effect failing to help; it is a large effect that cannot
reach the argmax.

**What all three have in common.** Weight changes, feasibility filters and a
restructured valuation all left the same candidate on top. A ranking that
refuses to move under three independent large perturbations is being decided
by a single dominant term, and everything else is rounding error against it.

The suspect is the monopoly term. `max_group_rent(...) / 2**missing` is
hundreds to low thousands, while list price is $60–$400 and projected rent is
tens of dollars. Any candidate touching a group we have presence in therefore
outranks every candidate that does not, regardless of price, rent, recipient
gain, or group interaction — which is precisely the invariance observed.

If that is right, it also explains refutation 2 without extra assumptions:
recipient gains computed from the same dominant term would be mis-signed on
exactly the trades where group structure changes hands, which is the ~50% of
the teacher's picks the filter rejected.

**Next test, and it is a cheap ablation, not a fit.** Rank by each component
*alone* — price only, rent only, monopoly only — on the fixed split, and
compare against the combined model's 12.7%/8.5%. Three outcomes, all
informative:

- monopoly-only reproduces the combined model → the term dominates as
  suspected, and the fix is scale, not structure;
- price-only or rent-only beats the combined model → the monopoly term is
  actively harmful and should be down-weighted or dropped;
- none of them reaches 12.7% → no single component carries the signal, and the
  valuation is wrong in kind rather than in proportion, which would mean the
  teacher is not ranking trades by a state-value difference at all.

That third outcome is worth taking seriously. If it lands, the next move is
not another valuation variant but a direct probe of *what the teacher's trade
choice actually correlates with*, measured rather than assumed.

**Phase 2 remains open.** No further valuation change until this ablation runs.

## D2.6 — Component ablation on the full pool, and the threshold-vs-ranking reconciliation

Run before anything from D2.5 is allowed into `SPEC.md`, on the full 400-board
pool (7,675 candidates, 118 proposals), board-level 60/40 split, Wilson 95%
intervals on every arm.

### Part 1 — which component drives the trade ranking

| arm | train top-1 | held-out top-1 |
| --- | --- | --- |
| combined (current) | 12.7% [6.8, 22.4] | 8.5% [3.4, 19.9] |
| **monopoly only** | **12.7% [6.8, 22.4]** | **8.5% [3.4, 19.9]** |
| price only | 7.0% [3.0, 15.4] | 4.3% [1.2, 14.2] |
| rent only | 5.6% [2.2, 13.6] | 8.5% [3.4, 19.9] |
| no monopoly | 5.6% [2.2, 13.6] | 4.3% [1.2, 14.2] |
| monopoly x0.1 | 8.5% [3.9, 17.2] | 6.4% [2.2, 17.2] |
| *random-pick reference* | *4.3%* | *4.3%* (mean 23.4 candidates) |

**The dominance hypothesis is confirmed, and not statistically — identically.**
Monopoly-only reproduces the combined model exactly on both splits (9/71 and
4/47, the same boards). Dropping the term costs more than half the accuracy.
This is the same fact the 40/40 argmax invariance showed, now with the cause
named: the ordering *is* the monopoly term, and price and rent are decoration.

**But the absolute numbers cannot support a SPEC rule.** The held-out interval
for every arm contains the 4.3% random-pick reference. At 47 proposals nothing
here is distinguishable from guessing, and the arms were chosen after seeing
earlier results, so train is not clean either. The correct statement is
"monopoly-only is identical to combined", which is an identity over the same
boards and does not need statistics. Any claim about which component ranks
*better* is unsupported and is not being made.

### Part 2 — the same perturbations on auction, a threshold decision

402 randomly configured auction states.

| arm | auction agreement | Δ vs combined |
| --- | --- | --- |
| combined (current) | 78.6% [74.3, 82.3] | — |
| price only | 79.4% [75.1, 83.0] | +0.7 |
| **no monopoly** | **83.6% [79.6, 86.9]** | **+5.0** |
| **monopoly x0.1** | **86.8% [83.2, 89.8]** | **+8.2** |
| monopoly only | 68.7% [64.0, 73.0] | −10.0 |
| rent only | 36.6% [32.0, 41.4] | −42.0 |

### Reconciliation — the proposed explanation is only half right

The hypothesis was: buy and auction survive a dominant monopoly term because
they compare one candidate against a fixed gate, where a term that shifts the
ceiling far above the standing bid is harmless, whereas ranking collapses under
a dominant additive term. Tested rather than assumed, it splits:

**Confirmed for buy — but for a more basic reason than proposed.** `_buy` does
not call `deed_value` at all; it is `gates_ok(env, pid, price)` and nothing
else. Buy's 96–98% is evidence about the safety gates exclusively and can be
cited neither for nor against the valuation. The apparent paradox for half the
cases was never a paradox; it was me quoting an agreement number for a code
path that does not exist.

**Refuted in its strong form for auction.** Auction is *not* insensitive to
the term. Removing it improves agreement by 5.0 points and shrinking it to a
tenth by 8.2 — well outside the intervals. The monopoly term is actively
harmful in auction too; auction merely survives it, at 78.6%, because price
and rent carry the decision (price-only alone scores 79.4%, and stripping rent
collapses it to 36.6%).

**What is actually true.** The same defect damages both decisions, by very
different amounts, and the threshold/ranking distinction explains the
*magnitude* rather than the presence:

- in a threshold comparison the term is one addend among three, so being wrong
  costs a bounded 5–8 points;
- in a ranking it is the *only* term that separates candidates, so being wrong
  costs everything — the ordering is fully determined by it.

So the finding is not "the monopoly term is fine for thresholds and bad for
rankings". It is **"the monopoly term is wrong, and ranking is simply the
decision that has no other term to fall back on."**

### Consequences

1. **Nothing from D2.5/D2.6 goes into `SPEC.md`.** These are findings about
   *our model*, not about the teacher's behaviour. `SPEC.md` documents
   observed teacher behaviour; a defect in `spec_model.py` belongs here.
2. **An immediate, measurable improvement is available and is not speculative**:
   scaling the monopoly term to 0.1 gains +8.2 points of auction agreement on
   402 states, interval [83.2, 89.8] against [74.3, 82.3]. That is worth
   taking on its own merits, independently of trade.
3. **The trade ranking still has no working model,** and the pool is too small
   to choose between candidate models. Widening it means more *proposal*
   boards, not more boards — 400 boards yielded only 118. The next step is a
   generator biased toward states where the teacher actually proposes, so the
   118 becomes ~500, before any further model is compared.
4. `max_group_rent / 2**missing` needs re-deriving from probe evidence rather
   than from the published formula. B3/B4/B5 measured *auction ceilings*, and
   ceilings constrain the term only up to the additive company it keeps —
   which is exactly the freedom that let a wrong term reproduce them.

## D2.7 — Monopoly x0.1 measured on the real distribution: it does not transfer

D2.6 measured scaling the monopoly term to 0.1 as worth **+8.2pp of auction
agreement** on 402 randomly generated auction states, [83.2, 89.8] against
[74.3, 82.3], non-overlapping. Applied and re-measured on held-out play, with
an A/B on **identical code** (the scale is now an env var so the two arms are
not two different commits):

| | scale 1.0 | scale 0.1 | Δ |
| --- | --- | --- | --- |
| auction | 90.5% | 88.7% | **−1.8** |
| turn flow | 93.3% | 88.3% | **−5.0** |
| development order | 30.3% | 29.1% | −1.2 |
| trade reply | 78.1% | 78.4% | +0.3 |
| trade proposal | 0.2% | 1.6% | +1.4 |
| **TOTAL (5,363 decisions)** | **73.4%** | **70.7%** | **−2.7** |

Auction moves **−1.8pp, not +8.2pp**, and the overall figure falls 2.7pp.
**Default reverted to 1.0.**

**This is the same failure mode for the fourth time,** and it is worth naming
plainly rather than filing as bad luck:

| # | narrow sample | conclusion | refuted by |
| --- | --- | --- | --- |
| 1 | p08 trade cell, 14 states, one board | rollout never changes trade decisions | Exp 6: 92.6% (D1.3) |
| 2 | p09, 80 states, one board shape | offer cheapest spare for the completing deed | held-out: 27/189 on the requested deed |
| 3 | p07, 224 states, one setup | never leaves jail in pre_roll | p10: 106/250 (D2.3) |
| 4 | D2.6, 402 random auction boards | monopoly x0.1 gains +8.2pp | this A/B: −1.8pp |

Case 4 is the sharpest because the sample was *large* (402 states, tight
intervals) and still wrong. Sample size was never the problem — **the
generator's distribution was**. Random deed allocations and random positions
do not produce the auction states that arise after teacher-driven play, and no
amount of widening a synthetic generator fixes a mismatch with the target
distribution.

**Standing rule from here:** a change is accepted only when measured on
held-out *play*, not on synthetically generated states. Synthetic probes stay
useful for isolating mechanism — that is what recovered A1–A6 and D1–D5 to the
dollar — but they do not decide whether a change ships. This should have been
the rule after case 1.

## D2.8 — First head-to-head: the clone is well short of the teacher

`bench.py`, 2 seats `spec` vs 2 seats `ASUValueV1`, seat-rotated across two
arrangements (spec on 0,2 then on 1,3), 30 games each, 60 total, all decisive.

| | |
| --- | --- |
| spec wins | 16 |
| teacher wins | 44 |
| **spec win rate** | **26.7%, 95% Wilson CI [17.1, 39.0]** |
| parity | 50.0% |

The interval excludes parity, so this is a real deficit, not noise. Per-seat
net worth tells the same story: spec averages $2.0k–$7.1k against the
teacher's $10.7k–$14.2k, and goes bankrupt in 80–93% of games against 57–70%.

This is the expected consequence of 73.4% agreement concentrated in the wrong
place: trade proposal is 16% of decisions at 0.2% agreement, and the clone
either proposes badly or ends its turn where the teacher trades. Phase 2's
acceptance also asks for the spec policy to be within 5 win-rate points of the
value teacher; at 26.7% vs 73.3% it is 46.6 points short.

**Note on what was benched.** The brief asked for `HeuristicRolloutPolicy`
from `heuristic_policy.py` with an early-denial bonus, versus `ASURolloutV1`.
Neither exists: `heuristic_policy.py` is absent from the tree (it was one of
the six phantom "existing starting points" recorded in D0.1) and no
early-denial exploit was built in any of this session's commits. The nearest
real measurement was run instead and is labelled as such. `ASUValueV1` was
used rather than `ASURolloutV1` because the 200-game rollout reference has now
run over 2.5 hours without completing a single game, so a rollout head-to-head
is not feasible at this budget.

## D2.9 — Harvesting real-play trades: the signal was there all along

D2.7's rule said changes ship only on held-out play. The corollary, applied
here, is that they should be *fitted* on the target distribution too. Instead
of widening the synthetic generator to ~500 boards, `harvest_trades.py`
collects the same decisions from 60 teacher-driven games:

| | synthetic (p09b) | harvested (real play) |
| --- | --- | --- |
| decision states | 400 | **6,032** |
| proposals | 118 | **2,508** |
| candidates | 7,675 | **358,042** |
| mean candidates / decision | 23.4 | 64.8 |

**The synthetic pool was not merely small — it was misleading.** On it, every
model scored ~8.5% against a 4.3% random reference, intervals overlapping, and
D2.5's third branch ("no component carries the signal") looked live. On real
play *every single feature* beats its 1.54% random reference, by 4× to 13×.
The signal was never absent; it was absent from the generated boards.

`analyze_trades.py` measured the decision rather than proposing a model. The
chosen candidate has a clear profile against the pool it was drawn from:

| quantity | chosen | pool avg |
| --- | --- | --- |
| requested deed, projected rent to us | **29.05** | 16.55 |
| requested deed, our deeds in its group | **0.98** | 0.45 |
| offered deed, projected rent to us | **6.51** | 11.44 |
| offered deed, list price | **156** | 189 |

It asks for high-rent deeds in groups it already holds part of, and gives away
cheap low-rent deeds from groups it does not. Best single feature — rent
difference — reaches 20.85% [18.43, 23.49] on its own.

`fit_trade_v2.py` searched weights on 1,520 train proposals (split by game
seed, since decisions inside a game share a board and would leak):

    held-out top-1  29.86%  [27.09, 32.79]      (988 proposals)
    rent only       20.85%
    random           1.54%

Train scored 25.72% — *below* held-out, so nothing is overfitted. The monopoly
term is deliberately absent from these features, per D2.6.

## D2.10 — Agreement up 4.1pp, win rate down: the objectives diverge

Fitted ranking plus a gate threshold (3.92, fitted on harvest train, 60.1%
held-out against a 57.4% never-propose baseline) applied to `spec_policy`:

| category | before | after |
| --- | --- | --- |
| trade proposal | 0.2% | **8.0%** |
| turn flow | 93.3% | **96.9%** |
| development order | 30.3% | **54.5%** |
| auction | 90.5% | 90.5% |
| **TOTAL held-out agreement** | **73.4%** | **77.5%** |

The gate matters more than the ranking: without it, proposals fire on every
positive score and steal END_TURN and build decisions (turn flow falls to
85.9%, development to 17.0%, total to 72.7%) even though trade proposal itself
reaches 25.3%. With it, trade proposal drops to 8.0% but everything else
recovers and the total gains 4.1pp.

**The head-to-head went the other way:**

| | spec wins | win rate |
| --- | --- | --- |
| before the trade fit | 16/60 | 26.7% [17.1, 39.0] |
| after | 12/60 | **20.0% [11.8, 31.8]** |

The intervals overlap heavily, so this is not a significant *decline* — but it
is certainly not the improvement the agreement gain predicts. **Imitation
fidelity and playing strength are different objectives, and this is the first
direct evidence of them diverging in this project.** A clone can match more of
the teacher's decisions while losing more games, because the decisions it
still gets wrong are not weighted by how much they cost.

That is worth stating plainly because Phase 2's two acceptance criteria assume
they move together: ">= 90% agreement" and "within 5 win-rate points of the
value teacher". At 77.5% and 20.0% the agent fails both, and closing the first
is not on its own a route to the second.

**Phase 2 status: still failing.**

| criterion | target | actual |
| --- | --- | --- |
| held-out decision agreement | >= 90% | **77.5%** |
| on-policy agreement (10 fresh games) | >= 85% | not yet measured |
| win rate vs value teacher | within 5 pts | **20.0% vs 80.0%** |

Remaining known defects, in order of measured cost: trade proposal is still
8.0% on 16% of decisions; trade reply sits at 78.1% on another 15%;
liquidation order is 23.8%; unmortgage 45.7%.

## D2.11 — Covariate shift in the trade fit: flagged, not yet critical

The trade ranking and gate (D2.9) were fitted on states harvested from **60
teacher-vs-teacher games** — seat 0 was `ASUValueV1` and so were, effectively,
the dynamics that produced every board it saw.

In a real match the agent plays `spec_policy` against the teacher. Two things
differ:

1. **The opponent is different.** The boards seat 0 encounters are produced by
   a teacher reacting to *spec's* moves, not to another teacher's. Deed
   allocations, cash levels and development trajectories will drift from the
   harvest distribution.
2. **Our own trajectory is different.** The harvest recorded states reached by
   a teacher playing optimally-by-its-own-lights. A clone at 77.5% agreement
   reaches materially different positions — typically worse ones, given it
   goes bankrupt in 86–93% of head-to-head games against the teacher's 60%.

This is ordinary covariate shift, and it is exactly what DAgger (Phase 3 in
the brief) exists to fix: iterate self-play, label the states the *clone*
visits, retrain.

**Not treated as critical yet**, because the fit is validated on held-out play
agreement (77.5%, up 4.1pp) which is measured on the same teacher-driven
distribution, and because the ranking's held-out top-1 (29.86%) was measured
on games the fit never saw. But the validation shares the harvest's bias, so
it cannot detect this failure mode.

**Trigger:** if a win-rate improvement lands materially below what the
agreement gain predicts, this is the first place to look — before any further
tuning of the ranking itself. D2.10 already shows one instance of agreement
rising while win rate did not, which is consistent with covariate shift
although not diagnostic of it on its own.

**Cheap check when needed:** re-harvest with seat 0 driven by `spec_policy`
instead of the teacher (the teacher still supplies the ground-truth label at
each state), refit, and compare. That is one DAgger iteration and it directly
tests whether the distribution is the problem.

## D2.12 — Cost-weighted defect ranking: agreement was ranking the wrong things

`pinned_ablation.py` pins one family at a time to the teacher's ground truth
and measures win-rate recovery. 40 seat-rotated games per arm.

**Harness validated first:** the `all` arm returns **50.0% [35.2, 64.8]** — an
agent pinned on every family is the teacher, and scores like it. Without that
check none of the other arms would mean anything.

| pinned family | win rate | Δ vs none | fires on | agreement |
| --- | --- | --- | --- | --- |
| none (baseline) | 27.5% [16.1, 42.8] | — | — | — |
| **trade_proposal** | **37.5% [24.2, 53.0]** | **+10.0** | 2.3% | 8.0% |
| liquidation | 27.5% [16.1, 42.8] | +0.0 | 4.6% | 23.8% |
| unmortgage | 27.5% [16.1, 42.8] | +0.0 | 0.8% | 45.7% |
| auction | 27.5% [16.1, 42.8] | +0.0 | 3.2% | 90.5% |
| turn_flow | 27.5% [16.1, 42.8] | +0.0 | 67.3% | 96.9% |
| development | 25.0% [14.2, 40.2] | −2.5 | 2.3% | 54.5% |
| trade_reply | 20.0% [10.5, 34.8] | −7.5 | 3.4% | 78.1% |
| all (upper bound) | 50.0% [35.2, 64.8] | +22.5 | 100% | — |

**The two rankings disagree, and the agreement one was wrong.**

- **Liquidation, agreement's worst family at 23.8%, costs nothing.** It fires
  on 4.6% of decisions and recovers exactly 0.0pp. Unmortgage (45.7%) the
  same. Both were near the top of the "fix next" list by agreement and both
  are worthless to fix. This is precisely the hypothesis that motivated the
  ablation.
- **Trade proposal is the only family with a positive effect**, +10.0pp on
  2.3% of decisions — **+4.34pp per 1% of decisions touched**, the best rate
  in the table by a wide margin.
- The gap between `all` (+22.5) and the sum of individual arms is large, which
  suggests the remaining loss is distributed or interactive rather than
  sitting in one family.

**Power caveat, stated before any allocation decision.** At 40 games per arm,
*every* interval overlaps the baseline's [16.1, 42.8]; only `all` is
distinguishable. The negative arms are almost certainly noise — pinning a
family to ground truth should not make play worse — and four arms landing on
exactly 11/40 indicates their changed decisions rarely flip a game rather than
that their effect is precisely zero. **This ranking is suggestive, not
settled.**

A confirmatory run over `none, trade_proposal, trade_reply` at 60 games per
arrangement (360 games, seeds 930000+) is in flight, using the streaming
version so it is visible and resumable.

**Provisional allocation, pending that run:** trade proposal first. It is both
the top of the cost ranking and still the worst-agreeing family with headroom
(8.0%), so the two rankings agree on it even though they disagree elsewhere.
Liquidation, unmortgage and auction are explicitly **de-prioritised despite
their agreement numbers** — that is the whole point of measuring cost.

## D2.13 — Confirmatory ablation: trade is the whole gap, and the two families are additive

480 games, 120 per arm, fresh seeds 930000+, seat-rotated. Three times the
games of the exploratory run, which was the right call — one of its findings
inverted.

| pinned family | win rate | Δ vs none | fires on | per 1% of decisions |
| --- | --- | --- | --- | --- |
| none | 26.7% [19.6, 35.2] | — | — | — |
| trade_reply | 33.3% [25.5, 42.2] | **+6.7** | 3.6% | +1.87pp |
| trade_proposal | 40.0% [31.7, 48.9] | **+13.3** | 2.6% | **+5.21pp** |
| **trade_both** | **45.8% [37.2, 54.7]** | **+19.2** | 4.3% | +4.49pp |

### Three results

**1. The n=40 negative was noise, exactly as suspected.** `trade_reply`
measured **−7.5pp** at 40 games and **+6.7pp** at 120 — it flipped sign. The
reasoning that rejected it ("pinning a family to ground truth should not make
play worse") held, and the insistence on more games before allocating was
correct. Had we acted on the exploratory run we would have written off a
family worth +6.7pp.

**2. The two families are additive; there is no interaction.**

    trade_proposal alone   +13.3
    trade_reply alone      + 6.7
    sum if independent     +20.0
    trade_both measured    +19.2   (difference −0.8pp, inside noise)

So the `trade_both` arm answers its question in the first of the three ways it
was set up to distinguish: the proposal fix stands on its own, the reply fix
stands on its own, and neither is hostage to the other. They can be worked
sequentially without one blocking the other.

**3. Fixing trade alone is statistically indistinguishable from parity.**
`trade_both`'s interval **[37.2, 54.7] contains 50.0%**, and 50% is parity by
construction in a 2v2 of identical policies. The `all` arm — every family
pinned — measured 50.0%. So trade accounts for essentially the entire gap
between the clone and the teacher: 26.7% → 45.8% of a 50% ceiling.

### This refutes my own earlier inference

D2.12 noted the gap between `all` (+22.5) and the sum of individual arms and
speculated that "the remaining loss is distributed or interactive rather than
sitting in one family", and that per-family fixes would therefore have a
ceiling well below parity with Phase 3 being the better route. **That was
wrong**, and it was wrong because it reasoned from underpowered arms. The loss
is highly concentrated: two families covering 4.3% of decisions carry ~19 of
the ~23 points.

### Allocation and Phase 3

**Allocation: trade_proposal first, trade_reply second.** Proposal is the most
efficient per decision touched (+5.21pp per 1%) and has the larger absolute
effect. Reply follows. Everything else — liquidation (23.8% agreement),
unmortgage (45.7%), auction, development, turn flow — stays de-prioritised;
the exploratory run measured all of them at +0.0pp and nothing here changes
that.

**Phase 3 is not the next move.** The hybrid/DAgger route was attractive on
the belief that the loss was distributed. It is not. A targeted fix to two
trade families has a measured ceiling of ~parity with the value teacher, which
is what Phase 2's acceptance actually asks for. Phase 3 should be reconsidered
after the trade work lands and its realised gain is compared against the
+19.2pp this predicts.

**D2.11's covariate-shift trigger is now armed and specific.** If the trade
fixes land materially below +19.2pp, the harvest distribution is the first
suspect — the fit came from teacher-vs-teacher games, and this ablation shows
trade decisions are precisely where the clone's play is decided.

## D2.14 — Additivity is provisional, and fitted models are the reason to doubt it

D2.13 measured `trade_both` (+19.2) against `trade_proposal` (+13.3) plus
`trade_reply` (+6.7), a −0.8pp residual, and concluded the two families are
independent. That conclusion is **provisional on one measurement**, and there
is a specific mechanism by which it could fail once both fixes are real code
rather than oracles.

**Why oracle additivity need not imply fitted additivity.** The oracle arms
substitute the teacher's *correct* action. Two correct components cannot
generate compounding error — each independently removes its own loss, so
additivity is close to guaranteed and the measurement mostly confirms the
absence of a strategic interaction (e.g. "good proposals are wasted if replies
are bad").

Fitted models are different. Both sides will be **wrong in correlated ways**,
because both are scored by the same deed-valuation features on the same board.
A proposal the fitted ranker likes for the wrong reason is exactly the kind of
trade the fitted reply rule is also likely to misjudge — and unlike the oracle
case, the two errors can reinforce. Concretely: the clone proposes a trade its
own valuation overrates, the opponent accepts because it is good *for them*,
and the reply rule that should have refused the mirror-image offer shares the
misvaluation that caused the proposal.

**So additivity must be re-tested, not inherited.** When both fixes are
implemented, run the three-way comparison again with fitted models in place of
oracles:

    fitted proposal only    vs floor
    fitted reply only       vs floor
    both fitted             vs floor

If `both` falls materially short of the sum, the two share a failure mode and
the shared component — the valuation — is the thing to fix, not either rule.
That would be the fourth time the valuation has been the root cause (D2.5,
D2.6, D2.12), which is itself a reason to expect it.

Recorded now so the check is not skipped by inertia once the first fix shows a
gain.

## D2.15 — Fitted vs oracle: the model captures ~37%, and that reverses the Phase 3 decision

Measured with the fitted trade model live in `spec_policy.py`, all three points
on the same seeds (930000+) and seat rotation:

| point | | win rate |
| --- | --- | --- |
| floor — proposals disabled (`TRADE_GATE=1e9`) | 15/80 | 18.8% [11.7, 28.7] |
| **fitted** — the 29.86% top-1 model | 32/120 | **26.7% [19.6, 35.2]** |
| oracle — teacher's actual proposal | 48/120 | 40.0% [31.7, 48.9] |

    fitted real gain   +7.9pp
    oracle ceiling    +21.3pp
    CAPTURE RATIO      37.3%

**The fitted model does convert to wins.** This also resolves D2.10, which
worried that agreement rose while win rate did not: that comparison used 60
games on different seeds and was noise. On matched seeds with more games the
fit is worth +7.9pp over never proposing.

**But it is not statistically significant on its own** — floor vs fitted gives
z = 1.29, p = 0.196, intervals overlapping. The point estimate is the best
available and the direction is consistent with the oracle result, but +7.9pp
is not established. Widening this specific comparison is cheap and should
happen before the number is leaned on hard.

### This reverses D2.13's Phase 3 recommendation

D2.13 deferred Phase 3 on the grounds that oracle-pinned trade reached parity,
so targeted fixes had a ceiling of ~parity. **That ceiling assumed perfect
trade decisions.** The fitted model reaches 37% of it, and there is no reason
to expect a second hand-fitted rule to do better — it would use the same
features on the same valuation.

Projection if `trade_reply` is fitted with the same method and captures the
same share:

    trade_reply fitted   ~ +2.5pp   (37% of its +6.7 oracle)
    total                ~ 29.2%    against parity of 50%

So hand-fitted rules plausibly get to ~29%, not ~46%. The remaining ~21 points
are inside the trade families but **not reachable by better weights on these
features** — three independent refutations (D2.5, D2.6, D2.12) already showed
the valuation, not the weighting, is the limit.

**That is precisely what Phase 3's learned component is for.** A network over
the 300-dim observation is not restricted to the four hand-chosen features
that cap the current ranker at 29.86% top-1, and DAgger addresses the
covariate shift flagged in D2.11 at the same time.

**Revised recommendation: proceed to Phase 3, and do not fit `trade_reply` by
hand first.** The evidence for that ordering:

1. per-family hand fitting has a measured capture of 37%, giving ~29% overall;
2. the binding constraint is the feature set, which Phase 3 replaces rather
   than reweights;
3. the trade families are where decisions are made (D2.13), so a learned
   component targeted there has the largest measured headroom in the project —
   ~21 points.

D2.13's "Phase 3 deferred" is superseded. It was reasoned from the oracle
ceiling, which is exactly the substitution this measurement was run to avoid.

**Additivity check (D2.14) is deferred with it.** It only becomes meaningful
once a second real implementation exists, and the recommendation is now not to
build that second implementation as a hand-fitted rule.
