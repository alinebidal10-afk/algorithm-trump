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

## Group B — the auction

Method note: in the auction phase the legal actions are PASS and four bid
increments (+1, +10, +50, +100), the increment being legal only if
`high_bid + increment <= cash`. Sweeping the standing bid `B` and finding the
smallest `B` at which the teacher passes locates its ceiling exactly, because
raising by +1 costs `B+1`: it passes precisely when `B+1` exceeds the ceiling.
Cash is pinned at $5,000 throughout so the safety gates never bind and the
ceiling reflects deed value alone.

### B1. The auction ceiling is several times list price
**Observation.** With no group presence, ceilings run 1.9×–7.4× list price:
Mediterranean $60 → $416 (6.9×), Oriental $100 → $546 (5.5×), Kentucky $220 →
$1,083 (4.9×), Boardwalk $400 → $2,315 (5.8×), Reading Railroad $200 → $388
(1.9×).
**Rule.** The teacher values a deed at auction far above its list price. It is
not anchored to price, and it will not be outbid by a price-anchored opponent.
**Confidence:** certain.
**Evidence:** `p02_auction_ceiling.csv` (82 rows, seed 20250811).

### B2. The value variant always opens at the maximum legal increment
**Observation.** `opening_action` is `auction_bid(+$100)` in **82/82** rows,
across every deed, colour and ownership configuration.
**Rule.** Given a ceiling above the standing bid, `ASUValueV1` jumps by the
largest legal increment rather than creeping. Combined with B1 this makes it
an aggressive, fast-escalating bidder.
**Confidence:** certain.
**Evidence:** `p02_auction_ceiling.csv`, `opening_action` column.
**See C2** — the rollout variant does the exact opposite, and this is where
the two disagree most.

### B3. Owning one deed of a three-deed group buys *no* premium
**Observation.** For every one of the 18 three-deed real-estate cases, the
ceiling with one group member already owned is **identical to the ceiling with
none owned** — ratio exactly 1.00, to the dollar:

| group | sq | own 0 | own 1 | own 2 | own1/own0 | own2/own1 |
| --- | --- | --- | --- | --- | --- | --- |
| green | 31 | 1377 | 1377 | 2641 | **1.00** | 1.92 |
| orange | 16 | 954 | 954 | 1835 | **1.00** | 1.92 |
| red | 21 | 1083 | 1083 | 2079 | **1.00** | 1.92 |
| pink | 11 | 775 | 775 | 1488 | **1.00** | 1.92 |
| lightblue | 6 | 546 | 546 | 1044 | **1.00** | 1.91 |
| yellow | 26 | 1212 | 1212 | 2324 | **1.00** | 1.92 |

(18/18 cases; the table shows one deed per group.)
**Rule.** The teacher pays the same for the *first* deed of a group as for the
*second*. Its bid escalates only on the deed that completes the monopoly.
**Confidence:** certain.
**Evidence:** `p02_auction_ceiling.csv`.

### B4. The completing deed roughly doubles the ceiling
**Observation.** `own2/own1` is 1.87–1.92 in all 18 three-deed cases (green
2641/1377 = 1.92, yellow 2324/1212 = 1.92, lightblue 1071/574 = 1.87).
**Rule.** Acquiring the deed that completes a monopoly is worth about twice
the marginal value of a non-completing deed of the same group.
**Confidence:** certain.
**Evidence:** `p02_auction_ceiling.csv`.

### B5. A group the player owns nothing of contributes no monopoly term
**Observation.** B3 and B4 together are not explained by a plain
`2 ** missing_deeds` discount, which predicts ratios 1 : 2 : 4 across
own0/own1/own2. Adding one clause does explain them exactly — that the
"before" state contributes a monopoly term **only if the player already owns
at least one deed of the group**. Marginal value is then

    M / 2**missing_after  -  (M / 2**missing_before  if owned_before > 0 else 0)

| | own0 | own1 | own2 |
| --- | --- | --- | --- |
| predicted ratio, 3-deed group | 1.00 | 1.00 | 2.00 |
| **observed** | **1.00** | **1.00** | **1.90–1.92** |
| predicted ratio, 2-deed group | 1.00 | 1.00 | — |
| **observed** (brown, darkblue) | **1.00** | **1.05–1.13** | — |

**Rule.** The monopoly term is gated on existing group presence, so the first
deed of a group is valued as if the group opportunity did not previously
exist. The residual 1.05–1.13 on two-deed groups is the base asset and
short-rent terms, which differ slightly between the two deeds.
**Confidence:** likely (the arithmetic matches to within the base-term
residual across 22 configurations, but the clause is inferred from ratios
rather than observed directly).
**Evidence:** `p02_auction_ceiling.csv`.

**Competitive note.** B3+B5 are an exploitable structural weakness, and they
sharpen Phase 5 module 2 (denial trading). The teacher will not bid defensively
for a group it has no presence in, and pays no premium for a second deed. An
opponent can therefore acquire the first two deeds of a group cheaply and only
faces competition on the third — by which point it holds the blocking
position. Recorded for Phase 5.

---

## Group C — rollout vs value divergence (Experiment 8, pulled forward)

Both variants are deterministic given a state — the rollout uses fixed
common-random-number streams — so repeating a state cannot yield a new answer.
The agreement rate is therefore estimated over a *population of constructed
boundary states*, not over RNG draws.

### C1. On boundary states the two variants disagree on a third of decisions
**Observation.** Over 230 constructed boundary states:

| category | n | diverge | rate | value s | rollout s | cost ratio |
| --- | --- | --- | --- | --- | --- | --- |
| auction | 56 | 53 | **94.6%** | 0.011 | 11.37 | 1035× |
| build | 48 | 28 | **58.3%** | 0.049 | 22.60 | 464× |
| buy | 112 | 0 | 0.0% | 0.043 | 4.78 | 112× |
| trade | 14 | 0 | 0.0% | 0.029 | 8.89 | 309× |
| **all** | **230** | **81** | **35.2%** | | | |

95% Wilson CI on the overall rate: **[29.3%, 41.6%]**.
**Rule.** Lookahead changes the decision often, but only in two families:
auctions and building. It never changed a buy or trade decision in this
corpus.
**Confidence:** certain (both policies are deterministic given a state, so the
null "rollout never changes the decision" is falsified outright).
**Evidence:** `p08_rollout_divergence.csv` (230 rows, seed 20250811).

### C2. Where they diverge, the rollout is systematically more liquidity-preserving
**Observation.** Every one of the 53 auction divergences is bid-versus-bid:
the value variant takes the largest increment (B2) while the rollout takes a
smaller one — in the certification scenario, `+$100` versus `+$1` on the same
state. The 28 build divergences fall into three patterns: `improve_house` vs
`improve_house` on a different square (11), `END_TURN` vs `mortgage` (10), and
`improve_house` vs `mortgage` (7) — the rollout raising cash where the value
variant either builds or does nothing.
**Rule.** Truncated lookahead consistently prefers holding liquidity: minimum
viable bids instead of maximum ones, and mortgaging instead of building.
**Confidence:** likely (the direction is consistent across all 81 divergences,
but "preserving liquidity" is an interpretation of the action pattern).
**Evidence:** `p08_rollout_divergence.csv`; corroborated independently by the
certification scenarios (`probes/certification/certification_result.txt`),
where 5 of 10 scenarios split value-vs-rollout in the same direction, and
identically under both `core.py` versions.

### C3. The earlier "10/10 agreement" was an artefact of ordinary play
**Observation.** On ordinary seed-3 play the variants agreed on 10/10 early
decisions; on constructed boundary states they disagree on 35.2%.
**Rule.** Most decisions in ordinary play are lopsided, so agreement there says
nothing about the value of lookahead. Divergence must be measured on states
selected for closeness, not sampled.
**Confidence:** certain.
**Evidence:** `p08_rollout_divergence.csv` vs `DECISIONS.md` D0.6.

---

## Status

| experiment | status |
| --- | --- |
| 0. Audit-trail certification (added) | done — PASS, 6,314 decisions, 0 mismatches |
| 1. Buy threshold curve | done — A1–A6 |
| 1b. Rent-residual mechanism (added) | done — A4, A5 |
| 2. Auction ceiling curve | done — B1–B5 |
| 3. Safety floor scaling | partial — floor located at $200 (A2); scaling with opponent development untested |
| 4. Development order | not started |
| 5. Mortgage / liquidation order | not started |
| 6. Trade accept/decline surface | not started |
| 7. Jail policy | not started |
| 8. Rollout-variant divergence | done (pulled forward) — C1–C3 |

**14 rules evidenced** (A1–A6, B1–B5, C1–C3) of the ≥25 required for Phase 1
acceptance. Experiments 3–7 remain.

### Rules by confidence

| confidence | rules |
| --- | --- |
| certain | A1, A2, A3, A4, A5, A6, B1, B2, B3, B4, C1, C3 |
| likely | B5, C2 |
| guess | — |

No rule has yet been contradicted by a later probe.
