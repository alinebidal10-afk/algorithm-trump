# SPEC.md — behavioural specification of the ASU frozen teacher

Every rule is stated as **observation → inferred rule → confidence**, and cites
the probe CSV that produced it. Rules are derived only from
`decide(env) -> action` outputs; no value component, safety breakdown or
rejection reason is read (see `DECISIONS.md` D0.3), and `core.py` /
`evaluate.py` have never been opened.

Confidence tags: **certain** (quantitatively predicted and confirmed to the
dollar), **likely** (consistent across a sweep, mechanism inferred),
**guess** (one observation, plausible reading).

Rule ids are stable. When a later probe contradicts a rule, the rule is kept,
its confidence downgraded, and the contradiction recorded beneath it.

---

## Audit Trail Integrity — certification of the probed teacher

**Verdict: PASS.** Probes in this document target a decision function proved
identical to the committed frozen teacher.

### Why a stronger check was needed

`ASU_FROZEN_TEACHER/core.py` carries 258 added / 32 removed uncommitted lines.
The initial evidence — a chained digest match on 3 ordinary-play seeds plus 24
green tests — was insufficient: three ordinary games are unlikely to reach
auctions with several live bidders, jail exits by card, forced liquidation,
bankruptcy resolution, trade acceptance, or the house/hotel boundary under a
constrained bank. If any of those branches had changed, the entire probe
corpus would rest on a policy nobody froze.

### What changed, by function name

Established from `git diff --numstat`, hunk headers, and a set-difference of
`def`/`class` names between `HEAD:core.py` and the working tree. Names only —
no diff body, and no decision logic, was read.

| | functions |
| --- | --- |
| **added** | `_DeedRentTables`, `_build_deed_rent_tables`, `_deed_rent_with`, `_expected_landings_items`, `_fast_copy_env`, `_fast_copy_player`, `_fast_copy_property`, `_fast_copy_trade_offer`, `_hypothetical_group_rent_uncached`, `_max_developed_rent_uncached` |
| **removed** | `_hypothetical_group_rent`, `_max_developed_rent`, `_owned_count` |
| **touched** | `deed_rent`, `expected_landings`, `liquidatable_worth`, `long_rent_projection`, `movement_probabilities`, `rent_projection`, `preserve_global_rng`, `_PrivateGame` |

The shape is memoisation plus renamed-behind-cache wrappers — with one
genuinely risky family. `_fast_copy_env / _fast_copy_player /
_fast_copy_property / _fast_copy_trade_offer` replace `deepcopy` in the
rollout's state duplication. A hand-rolled copy that omits a rarely-populated
field (auction bidders, pending trades, debt bookkeeping) would reproduce
ordinary play exactly while corrupting precisely the rare branches above.
That risk is what the certification had to exclude.

### Method

Not a comparison against a stored digest, which only fixes behaviour on the
three seeds that produced it. Instead **both versions were executed and their
outputs diffed.** `HEAD:ASU_FROZEN_TEACHER/core.py` was checked out into a
shadow package placed first on `sys.path`; `certify_teacher.py` runs under
each version and emits the selected action id at every decision point.

This reads no source at all — each version is executed, never inspected — and
it records only selected action ids, so the D0.3 opacity discipline holds
here too.

| | |
| --- | --- |
| old `core.py` sha256 | `09d84f268c9f7e99…` (git `HEAD`) |
| new `core.py` sha256 | `4ea57aa919de4735…` (working tree) |
| ordinary-play seeds | 20 (seeds 1–20, value variant, full games to 1200 steps) |
| rollout seeds | 5 (seeds 1–5, 20 decisions each — exercises `_fast_copy_*`) |
| synthetic scenarios | 10, each run under **both** variants |
| **decision points compared** | **6,314** |
| **mismatches** | **0** |

The 10 scenarios cover every branch named above: a four-bidder auction for
Boardwalk; jail exit by bail, by card, and at the third-turn boundary; forced
liquidation under a $1,100 debt; bankruptcy with nothing left to liquidate;
an incoming trade priced to accept and one priced to refuse; and the
4-house/hotel boundary with the bank down to 2 houses and 1 hotel, against an
unconstrained control. Each was verified to actually reach its branch before
being trusted — the first trade scenario exposed only offer-*making* actions,
so real `TradeOffer` objects were injected until `ACCEPT_TRADE` and
`DECLINE_TRADE` became legal.

### Certification

Across 6,314 decision points spanning 20 full ordinary-play seeds, 5 rollout
seeds, and 10 synthetic scenarios chosen specifically to reach the rare
branches that the `_fast_copy_*` family could plausibly have broken, the
modified `core.py` selected an identical action to the committed `core.py` at
**every single decision point**, under both the value and the rollout variant.
The change is therefore behaviour-preserving on the decision function, and the
3× speedup (0.0501 → 0.0167 s/decision aggregate) is a pure optimisation. The
probe corpus in this document is valid evidence about the frozen teacher.

Artifacts: `probes/certification/` (`cert_old_core.json`,
`cert_new_core.json`, `certification_result.txt`, `versions.txt`).
Reproduce with `certify_teacher.py --emit old --shadow <dir>` /
`--emit new`, then `--compare`.

**Standing check.** Re-run this certification if `core.py` is touched again.
A digest-only check against `artifacts/asu_baseline_locked.json` is not a
substitute and should not be treated as one.

---

## Group A — the buy decision

### A1. Buy response is monotone in cash
**Observation.** For all 28 deeds, sweeping cash from list price to price +
2500 in $25 steps, the teacher's buy/skip response flips exactly once and
never flips back (`monotone = True`, 28/28).
**Rule.** For a fixed board, `BUY` is chosen iff cash ≥ a single deed-specific
threshold. A per-deed "flip point" is therefore well defined.
**Confidence:** certain.
**Evidence:** `p01_buy_threshold.csv` (28 rows, `monotone` column, seed 20250811).

### A2. The buy gate is a floor on cash *after* the purchase, not on cash
**Observation.** On an empty board with all opponents on Go, the flip point is
`price + 200` for 21 of 28 deeds — across prices from $60 (Mediterranean) to
$400 (Boardwalk), the *difference* is pinned at exactly 200 while the price
varies 6.7×.
**Rule.** The teacher buys only if the post-purchase cash balance clears a
fixed floor of **$200**. The gate is on `cash - price`, not on `cash` and not
on any multiple of price.
**Confidence:** certain.
**Evidence:** `p01_buy_threshold.csv`, `flip_minus_price` column.

### A3. The floor is offset by projected rent income, not applied bare
**Observation.** The 7 deeds that flipped *below* `price + 200` in p01 were
squares 5, 6, 8, 9, 11, 12, 15 — precisely the deeds reachable from Go by one
2d6 roll, with the opponents parked on Go. Holding the deed fixed and walking
the opponents instead (p01b) reproduces the effect on deeds that showed no
residual at all: Boardwalk's flip point falls from 600 to 575 as three
opponents move from 1 to 7 squares behind it.
**Rule.** The gate is

    (cash - price) + E[next-round net rent] >= 200

**Confidence:** certain.
**Evidence:** `p01_buy_threshold.csv` (residual deeds), `p01b_rent_residual.csv`
(70 rows, 5 deeds × 14 opponent distances).

### A4. The rent projection is an exact 2d6 landing enumeration × rent, summed over opponents
**Observation.** With three opponents parked `g` squares behind the target
deed, the residual `price + 200 - flip_cash` tracks
`3 × P(2d6 = g) × base_rent` to the dollar over gaps 1–8, for deeds of
different rent:

| gap | P(2d6=g)·3·$50 (Boardwalk) | observed | P(2d6=g)·3·$20 (Illinois) | observed |
| --- | --- | --- | --- | --- |
| 1 | 0.0 | 0 | 0.0 | 0 |
| 2 | 4.2 | 4 | 1.7 | 1 |
| 3 | 8.3 | 8 | 3.3 | 3 |
| 4 | 12.5 | 12 | 5.0 | 5 |
| 5 | 16.7 | 16 | 6.7 | 6 |
| 6 | 20.8 | 21 | 8.3 | 8 |
| 7 | **25.0** | **25** | **10.0** | **10** |
| 8 | 20.8 | 21 | 8.3 | 8 |

The peak sits at gap 7 (the 2d6 mode) and the curve is symmetric about it.
Residual scales linearly in rent: the Boardwalk/Illinois ratio is 25/10 =
2.5 = 50/20, the ratio of base rents.
**Rule.** Expected rent income is computed by enumerating the 2d6 landing
distribution over each opponent's *actual board position* — not a uniform lap
model — and multiplying by the rent that deed would charge.
**Confidence:** certain.
**Evidence:** `p01b_rent_residual.csv`.

### A5. The projection includes doubles-driven extra rolls
**Observation.** For gaps 9–14 the observed residual consistently *exceeds*
the single-roll prediction, and is non-zero where a single 2d6 roll cannot
reach at all: gap 13 → residual 1 and gap 14 → residual 2 against a
single-roll prediction of 0.0 (Boardwalk). The excess grows with gap.

| gap | single-roll prediction | observed |
| --- | --- | --- |
| 9 | 16.7 | 18 |
| 10 | 12.5 | 14 |
| 11 | 8.3 | 9 |
| 12 | 4.2 | 6 |
| 13 | 0.0 | 1 |
| 14 | 0.0 | 2 |

**Rule.** The landing enumeration models a *complete turn*, not a single roll:
rolling doubles grants another roll, so squares 13–24 ahead are reachable with
positive probability. This matches the published description of a five-turn
complete-turn enumeration.
**Confidence:** certain (the non-zero mass beyond gap 12 is unreachable in one
roll, so it cannot be explained any other way).
**Evidence:** `p01b_rent_residual.csv`, gaps 9–14.

### A6. Rent is projected from opponents' real positions, giving a positional bias to deed value
**Observation.** A1–A5 taken together: two deeds with identical price and rent
have different buy thresholds purely because opponents stand at different
distances from them (p01b, gap 7 vs gap 1: 575 vs 600 for the same deed on the
same board).
**Rule.** Deed valuation is position-dependent and recomputed per decision.
There is no static per-deed price table.
**Confidence:** certain.
**Evidence:** `p01b_rent_residual.csv`.

**Competitive note.** A3–A6 show the teacher already models rent it will
*collect* from opponents' true positions. This narrows Phase 5 module 1: the
gap to exploit is rent *paid to* opponents from their developed holdings, not
the collection side, which is already sharp. Recorded in `DECISIONS.md`.

---

## Status

| experiment | status |
| --- | --- |
| 1. Buy threshold curve | done — A1–A6 |
| 1b. Rent-residual mechanism (added) | done — A4, A5 |
| 2. Auction ceiling curve | not started |
| 3. Safety floor scaling | partial — floor located at $200 (A2); scaling with opponent development untested |
| 4. Development order | not started |
| 5. Mortgage / liquidation order | not started |
| 6. Trade accept/decline surface | not started |
| 7. Jail policy | not started |
| 8. Rollout-variant divergence | not started; 10/10 agreement seen in ordinary play (`DECISIONS.md` D0.6) means this needs adversarial states |

**6 rules evidenced of the ≥25 required for Phase 1 acceptance.** Phase 1 is
not complete.
