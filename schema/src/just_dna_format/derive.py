"""Legacy → 0.3 column derivations (the "upgrade" back-population) and the read-time aliases that let
a consumer see the orthogonal 0.3 axes even on a 0.1/0.2 module that only set `state`.

Kept as a leaf module (it imports nothing from `spec`) so both `spec` — for its `effective_*`
accessors and `upgraded()` — and external consumers (the marketplace `revalidate`/`needs_upgrade`
flow) can import these pure functions without an import cycle.

`state` and the ClinVar booleans stay **required/authoritative** for 0.2 backward-compat
(CONSTITUTION Principle 3 forbids making a required field optional inside a major); the new axes are
optional, with these derivations as their fallback. Every function here is **total and idempotent**:
applying it to an already-derived value is a no-op (CONSTITUTION Principle 7). See the
"Upgrade derivation" section of docs/COMPILER.md.
"""

from typing import Optional

# The "Upgrade derivation" mapping (docs/COMPILER.md): legacy `state` → (direction, stat_significance).
_STATE_TO_DIRECTION: dict[str, str] = {
    "protective": "protective",
    "risk": "risk",
    "neutral": "neutral",
    "significant": "unknown",  # significance is not a direction; refined from weight sign below
    "alt": "unknown",
    "ref": "unknown",
}
_STATE_TO_STAT_SIGNIFICANCE: dict[str, str] = {
    "protective": "unknown",
    "risk": "unknown",
    "neutral": "unknown",
    "significant": "significant",
    "alt": "unknown",
    "ref": "unknown",
}
# The trimmed legacy set an upgraded module emits: `unknown` collapses to `neutral`.
_DIRECTION_TO_STATE: dict[str, str] = {
    "protective": "protective",
    "risk": "risk",
    "neutral": "neutral",
    "unknown": "neutral",
}


def direction_from_state(state: str, weight: Optional[float] = None) -> str:
    """Derive `direction` from the legacy `state` (plus the `weight` sign when informative).

    `significant` carries no direction on its own, so it is refined from the weight sign when present
    (positive → protective, negative → risk); otherwise it, and the retired `alt`/`ref` descriptors,
    map to the honest `unknown` the old enum lacked."""
    if state == "significant" and weight is not None:
        if weight > 0:
            return "protective"
        if weight < 0:
            return "risk"
    return _STATE_TO_DIRECTION.get(state, "unknown")


def stat_significance_from_state(state: str) -> str:
    """Derive `stat_significance` from the legacy `state` (only `significant` is informative)."""
    return _STATE_TO_STAT_SIGNIFICANCE.get(state, "unknown")


def trimmed_state(direction: str) -> str:
    """Project a `direction` back into the trimmed legacy `state` set {protective, risk, neutral}
    (`unknown` → `neutral`). This is the derived, deprecated `state` an upgraded module emits."""
    return _DIRECTION_TO_STATE.get(direction, "neutral")


def clin_sig_from_booleans(
    pathogenic: Optional[bool], benign: Optional[bool], clinvar: Optional[bool]
) -> Optional[str]:
    """Derive a `clin_sig` tier from the lossy legacy ClinVar booleans.

    `pathogenic` → pathogenic; `benign` → benign; in-ClinVar with neither flag →
    uncertain_significance; otherwise None (nothing to say). Lossy by construction — legacy cannot
    recover `likely_pathogenic`/`likely_benign`."""
    if pathogenic:
        return "pathogenic"
    if benign:
        return "benign"
    if clinvar:
        return "uncertain_significance"
    return None


def pathogenic_from_clin_sig(clin_sig: Optional[str]) -> Optional[bool]:
    """The `pathogenic` boolean implied by a `clin_sig` tier: True for the pathogenic tiers, else
    None (the tier is silent on the boolean — we never fabricate a `False` a curator did not state)."""
    if clin_sig in {"pathogenic", "likely_pathogenic"}:
        return True
    return None


def benign_from_clin_sig(clin_sig: Optional[str]) -> Optional[bool]:
    """The `benign` boolean implied by a `clin_sig` tier: True for the benign tiers, else None."""
    if clin_sig in {"benign", "likely_benign"}:
        return True
    return None
