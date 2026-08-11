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
exchange pairs.** It is calibrated well enough for threshold decisions — where
only its comparison against a cash gate matters, hence 96% on buy and 91% on
auction — but ranking two deeds against each other needs relative accuracy it
does not have.

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
enough for thresholds (buy 98.4%, auction 90.5%) but not for ranking two deeds
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
