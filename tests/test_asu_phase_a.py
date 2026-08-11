"""
tests/test_asu_phase_a.py
--------------------------
Phase A regression coverage for the ASU_FROZEN_TEACHER performance work:

(a) Digest regression: the chained SHA-256 decision digests for seeds
    3, 7, 11 (as produced by ``tools/asu_baseline.py``) must still equal
    the locked constants in ``artifacts/asu_baseline_locked.json``.
(b) Cache on/off equivalence for ``_max_developed_rent`` and
    ``_hypothetical_group_rent``: the lru_cache-wrapped function must
    return exactly what its ``_uncached`` twin returns, for a handful of
    hand-built argument tuples.
(c) Cache-key completeness for ``_max_developed_rent``: starting from one
    base argument tuple, vary each argument in turn and confirm the
    cached function still agrees with the uncached one -- this catches a
    cache key that silently ignores one of the arguments (stale hits).
(d) The frozen spec hash must not have moved.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.asu_baseline import SEEDS, run_seed  # noqa: E402

from ASU_FROZEN_TEACHER.core import (  # noqa: E402
    _hypothetical_group_rent,
    _hypothetical_group_rent_uncached,
    _max_developed_rent,
    _max_developed_rent_uncached,
)
from ASU_FROZEN_TEACHER.spec import FROZEN_SPEC_HASH  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────
# (a) Digest regression
# ─────────────────────────────────────────────────────────────────────────

LOCKED_DIGESTS = {
    3: "65a666333635d9f837e7610fe25083761348e9aeb17a2e2453be4f6c690dc266",
    7: "deba3445cdd4eb9f2e9467a1c606470408c119f9e7ac487924462db302469f7d",
    11: "144b23efba152c4d16f5dec393e40f6c1c7ff962c7bebc67013528842ae42629",
}


def test_locked_seeds_match_baseline_seeds() -> None:
    assert set(SEEDS) == set(LOCKED_DIGESTS)


@pytest.mark.parametrize("seed", sorted(LOCKED_DIGESTS))
def test_decision_digest_matches_locked_baseline(seed: int) -> None:
    result = run_seed(seed)
    assert result["digest"] == LOCKED_DIGESTS[seed]


# ─────────────────────────────────────────────────────────────────────────
# (b) Cache on/off equivalence
# ─────────────────────────────────────────────────────────────────────────

# color, squares, levels, enabled, budget, houses_available, hotels_available
_MAX_DEVELOPED_RENT_CASES = [
    ("brown", (1, 3), (0, 0), (True, True), 200.0, 32, 12),
    ("lightblue", (6, 8, 9), (1, 2, 0), (True, True, True), 500.0, 10, 5),
    ("railroad", (5, 15, 25, 35), (0, 0, 0, 0), (True, True, False, True), 0.0, 32, 12),
    ("utility", (12, 28), (0, 0), (True, False), 0.0, 32, 12),
    ("darkblue", (37, 39), (4, 3), (True, True), 800.0, 2, 1),
    ("green", (31, 32, 34), (0, 4, 4), (True, True, False), 1000.0, 0, 2),
]


@pytest.mark.parametrize("args", _MAX_DEVELOPED_RENT_CASES)
def test_max_developed_rent_cache_matches_uncached(args) -> None:
    assert _max_developed_rent(*args) == _max_developed_rent_uncached(*args)


@pytest.mark.parametrize("args", _MAX_DEVELOPED_RENT_CASES)
def test_hypothetical_group_rent_cache_matches_uncached(args) -> None:
    color, squares, levels, enabled = args[:4]
    assert _hypothetical_group_rent(
        color, squares, levels, enabled
    ) == _hypothetical_group_rent_uncached(color, squares, levels, enabled)


# ─────────────────────────────────────────────────────────────────────────
# (c) Cache-key completeness for _max_developed_rent
# ─────────────────────────────────────────────────────────────────────────

_BASE_ARGS = ("lightblue", (6, 8, 9), (1, 1, 1), (True, True, True), 300.0, 10, 5)

_ARG_VARIANTS = [
    ("color", "pink"),
    ("squares", (6, 8, 13)),
    ("levels", (2, 1, 1)),
    ("enabled", (True, False, True)),
    ("budget", 500.0),
    ("houses_available", 20),
    ("hotels_available", 8),
]

_ARG_NAMES = (
    "color",
    "squares",
    "levels",
    "enabled",
    "budget",
    "houses_available",
    "hotels_available",
)


@pytest.mark.parametrize("field, replacement", _ARG_VARIANTS)
def test_max_developed_rent_cache_key_completeness(field, replacement) -> None:
    index = _ARG_NAMES.index(field)
    variant = list(_BASE_ARGS)
    variant[index] = replacement
    variant = tuple(variant)

    assert variant != _BASE_ARGS
    assert _max_developed_rent(*variant) == _max_developed_rent_uncached(*variant)
    # And the unmodified base tuple must still be unaffected by whatever the
    # cache did for the variant (i.e. no cross-key contamination).
    assert _max_developed_rent(*_BASE_ARGS) == _max_developed_rent_uncached(*_BASE_ARGS)


# ─────────────────────────────────────────────────────────────────────────
# (d) Frozen spec hash
# ─────────────────────────────────────────────────────────────────────────


def test_frozen_spec_hash_unchanged() -> None:
    assert (
        FROZEN_SPEC_HASH
        == "9ab1907e0de1af4b253ce36ffa107c4fdb5e2b913858ef87c362423e61a6fd74"
    )
