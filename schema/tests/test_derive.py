"""0.3 upgrade derivation + read-time aliases (ROADMAP "Upgrade derivation" table; CONSTITUTION
Principles 7 & 8). Covers: `state`(+`weight`) → `direction`/`stat_significance`, the ClinVar
booleans ↔ `clin_sig` aliasing, the non-mutating `effective_*` accessors, and — the invariant that
matters most — that `upgraded()` is idempotent and that `state`/booleans stay authoritative
(required) rather than being overwritten when a curator set the new axis explicitly."""

import pytest
from just_dna_format.derive import (
    clin_sig_from_booleans,
    direction_from_state,
    stat_significance_from_state,
    trimmed_state,
)
from just_dna_format.spec import VariantRow


def _row(**overrides: object) -> VariantRow:
    base: dict[str, object] = {
        "rsid": "rs1801133",
        "genotype": "A/G",
        "state": "risk",
        "conclusion": "example",
    }
    base.update(overrides)
    return VariantRow(**base)  # type: ignore[arg-type]


# ── The ROADMAP "Upgrade derivation" table, verbatim ─────────────────────────────
# old state | weight | → direction | → stat_significance | trimmed state
_TABLE = [
    ("protective", None, "protective", "unknown", "protective"),
    ("risk", None, "risk", "unknown", "risk"),
    ("neutral", None, "neutral", "unknown", "neutral"),
    ("significant", None, "unknown", "significant", "neutral"),
    ("significant", 0.5, "protective", "significant", "protective"),  # refined from weight sign
    ("significant", -0.5, "risk", "significant", "risk"),
    ("alt", None, "unknown", "unknown", "neutral"),
    ("ref", None, "unknown", "unknown", "neutral"),
]


@pytest.mark.parametrize("state,weight,direction,stat_sig,tstate", _TABLE)
def test_state_derivation_matches_roadmap_table(
    state: str, weight: float | None, direction: str, stat_sig: str, tstate: str
) -> None:
    assert direction_from_state(state, weight) == direction
    assert stat_significance_from_state(state) == stat_sig
    assert trimmed_state(direction) == tstate
    # And through the row accessors + upgrade:
    row = _row(state=state, weight=weight)
    assert row.effective_direction == direction
    assert row.effective_stat_significance == stat_sig
    up = row.upgraded()
    assert up.direction == direction
    assert up.stat_significance == stat_sig
    assert up.state == tstate  # legacy `state` kept, trimmed to a derived mirror of `direction`


def test_effective_direction_respects_an_explicit_value() -> None:
    # A curator-set `direction` is authoritative and must NOT be overwritten by the `state` mapping.
    row = _row(state="neutral", direction="risk")
    assert row.effective_direction == "risk"
    assert row.upgraded().direction == "risk"
    assert row.upgraded().state == "risk"  # trimmed from the explicit direction, not from `state`


def test_clin_sig_from_booleans() -> None:
    assert clin_sig_from_booleans(True, False, True) == "pathogenic"
    assert clin_sig_from_booleans(False, True, True) == "benign"
    assert clin_sig_from_booleans(None, None, True) == "uncertain_significance"
    assert clin_sig_from_booleans(None, None, None) is None


def test_clin_sig_boolean_aliases_both_directions() -> None:
    # booleans → clin_sig
    assert _row(pathogenic=True).effective_clin_sig == "pathogenic"
    assert _row(benign=True).effective_clin_sig == "benign"
    assert _row(clinvar=True).effective_clin_sig == "uncertain_significance"
    assert _row().effective_clin_sig is None
    # clin_sig → booleans (never fabricates a False the curator did not state)
    assert _row(clin_sig="likely_pathogenic").effective_pathogenic is True
    assert _row(clin_sig="likely_benign").effective_benign is True
    assert _row(clin_sig="risk_factor").effective_pathogenic is None
    assert _row(clin_sig="risk_factor").effective_benign is None


def test_upgrade_is_idempotent() -> None:
    # CONSTITUTION Principle 7: a derivation is a fixed point.
    for row in (
        _row(state="significant", weight=-0.2, clinvar=True),
        _row(state="protective", pathogenic=True),
        _row(state="alt", benign=True, clin_sig="uncertain_significance"),
    ):
        once = row.upgraded()
        assert once.upgraded() == once


def test_needs_upgrade_flags_only_drifted_rows() -> None:
    legacy = _row(state="risk")  # has state, lacks the 0.3 axes
    assert legacy.needs_upgrade is True
    assert legacy.upgraded().needs_upgrade is False  # upgrading resolves the drift
