"""
Shared constrained vocabularies, identifier patterns, and reusable validator helpers.

A dependency-light leaf (stdlib only) so every authored-DSL model — `spec` (variants/studies),
`binning` (the measure→phenotype primitive), `pgx` (star-alleles), and `pgs` — validates against
one source of truth for the orthogonal axes and identifier grammars. Per CONSTITUTION Principle 6,
constrained vocabularies are `frozenset[str]` + a validator, never `Enum`/`Literal`.

`spec` re-exports the names it historically owned, so existing imports
(`from just_dna_format.spec import VALID_DIRECTIONS`) keep working unchanged.
"""

import math
import re
from typing import Optional

# ── Orthogonal axis vocabularies (the 0.3 split out of the overloaded `state`) ──────────────────
# Effect direction — the clean phenotypic scalar. Orthogonal to `clin_sig` and `stat_significance`.
VALID_DIRECTIONS: frozenset[str] = frozenset({"protective", "risk", "neutral", "unknown"})
# Graduated statistical significance (named `stat_significance`, NOT `significance` — that is the
# clinical axis).
VALID_SIGNIFICANCE: frozenset[str] = frozenset(
    {"significant", "suggestive", "not_significant", "unknown"}
)
# ClinVar / ACMG clinical significance (VEP `CLIN_SIG` vocabulary). Distinct from `direction`.
VALID_CLIN_SIG: frozenset[str] = frozenset(
    {
        "pathogenic",
        "likely_pathogenic",
        "uncertain_significance",
        "likely_benign",
        "benign",
        "drug_response",
        "association",
        "risk_factor",
        "protective",
        "affects",
        "conflicting",
        "not_provided",
        "other",
    }
)

# ── Identifier grammars ─────────────────────────────────────────────────────────────────────────
RSID_PATTERN: re.Pattern[str] = re.compile(r"^rs\d+$")
ALLELE_PATTERN: re.Pattern[str] = re.compile(r"^[ACGT]+$", re.IGNORECASE)
# EFO/MONDO/OBA/HP-style ontology CURIE, e.g. EFO_0001645 or MONDO:0005265 (matches just-prs's
# `trait_efo_id`). Multiple ids may be given, comma/semicolon/pipe-separated.
TRAIT_ID_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z][A-Za-z]*[:_]\w+$")
# Separators accepted inside a multi-valued CSV cell (`flags`, `trait_efo_id`, `training_ancestry`).
MULTI_SEP: re.Pattern[str] = re.compile(r"[,;|]")

# ── Reserved namespace (0.4) ──────────────────────────────────────────────────────────────────
# Names reserved against the one-way door but deliberately NOT built this run (see docs/PROPOSAL_0_4
# §T2/A4/B6 + round-2). The 0.4 tables set `model_config = ConfigDict(extra="forbid")`, so a column
# bearing one of these is rejected until a future release claims it. `reference_sequence`,
# `suballele`, `tissue`, `assay_context`, and `source_field` are BUILT this run, so they are absent
# here.
RESERVED_NAMES_0_4: frozenset[str] = frozenset(
    {
        # The provenance triple stays reserved: it describes which tool made a *call* (a consumer's
        # computed measurement), not annotation — so by the data-agnostic north star it is
        # consumer-side, never a module column (round-2 Q2).
        "caller",
        "caller_version",
        "reference_db",
        "callable_from",  # round-2 3d/0.5 — VCF-derived three-state callability signal (DP,GQ,FT)
    }
)
# NOTE: `requires_callable`, `acmg_sf`, `actionability` were reserved here and are now BUILT as
# optional `VariantRow` columns (they are general per-variant annotation refinements). PharmGKB
# `drug`/`response`/`evidence_level` are built on `PharmVariantRow`/`DiplotypeRow`. So none of those
# are reserved any longer.

# PharmGKB clinical-annotation evidence levels (item 9). Closed vocabulary (Principle 6).
VALID_EVIDENCE_LEVELS: frozenset[str] = frozenset({"1A", "1B", "2A", "2B", "3", "4"})

# ── Module authorship (RM14; docs/USE_CASES.md §5a) ─────────────────────────────
# A contribution's `role` is a small, stable, CLOSED vocabulary (Principle 6): what a contributor did
# to *this version*.
VALID_AUTHOR_ROLES: frozenset[str] = frozenset({"created", "edited", "audited", "reviewed"})
# A contributor's `kind` is an OPEN, multi-valued tag set — a *recommended seed* keyed for consumer
# faceting (route scrutiny by author-kind), but authors may coin new tags as AI topologies proliferate,
# so unknown tags are kept, not rejected (like `flags`). Facets:
#   • human, a rising ladder of assurance: `human` → `human_expert` → `human_certified`
#     (a medically / board-certified expert, e.g. a clinical geneticist);
#   • ai, plus a scale/topology tag: `ai` with `agent` | `team` | `swarm`.
# There is deliberately **no `hybrid` tag** — it was rejected as non-explicit (hybrid *what* — a human
# + a small model, or a certified expert + a SOTA swarm?). A joint contribution is expressed by two
# entries (a human and an ai), each with its own `kind`, so the mix is always spelled out.
RECOMMENDED_AUTHOR_KINDS: frozenset[str] = frozenset(
    {"human", "human_expert", "human_certified", "ai", "agent", "team", "swarm"}
)
# The reserved `actionability` axis's recommended seed vocabulary (documentation — the field is not
# built yet, so this is not enforced). Round-2 Q9 extended the round-1 seed with `descriptive` (a
# large fraction of findings are self-knowledge / no-action — an explicit "none", not forced into
# `actionable`) and `modifiable` (lifestyle-actionable, distinct from clinical `actionable`).
ACTIONABILITY_SEED: frozenset[str] = frozenset(
    {"actionable", "preventable", "pharmacogenomic", "incurable", "reproductive", "descriptive", "modifiable"}
)


def check_vocab(value: Optional[str], vocab: frozenset[str], field_name: str) -> Optional[str]:
    """Validate an optional categorical against a closed `frozenset` vocabulary (Principle 6).

    Passes `None` through (absent = unknown). The message format matches the pre-refactor
    per-field validators exactly (`<field> must be one of [...], got: <value>`)."""
    if value is not None and value not in vocab:
        raise ValueError(f"{field_name} must be one of {sorted(vocab)}, got: {value!r}")
    return value


def validate_trait_ids(value: Optional[str], field_name: str = "trait_efo_id") -> Optional[str]:
    """Validate a multi-valued CURIE cell: each `[,;|]`-split token must be an ontology CURIE."""
    if value is None:
        return value
    for tok in MULTI_SEP.split(value):
        tok = tok.strip()
        if tok and not TRAIT_ID_PATTERN.match(tok):
            raise ValueError(
                f"{field_name} tokens must be ontology CURIEs like EFO_0001645 / "
                f"MONDO:0005265, got: {tok!r}"
            )
    return value


def validate_allele(value: Optional[str], field_name: str = "allele") -> Optional[str]:
    """Validate an optional nucleotide string (`^[ACGT]+$`, case-insensitive)."""
    if value is not None and not ALLELE_PATTERN.match(value):
        raise ValueError(f"{field_name} must be nucleotides (e.g. A, G, AC), got: {value!r}")
    return value


def validate_rsid(value: Optional[str]) -> Optional[str]:
    """Validate an optional dbSNP identifier (`rs<digits>`)."""
    if value is not None and not RSID_PATTERN.match(value):
        raise ValueError(f"rsid must match rs<digits>, got: {value!r}")
    return value


def validate_finite(value: Optional[float], field_name: str) -> Optional[float]:
    """Reject a non-finite float (`NaN`/`inf`). A `NaN` breaks round-trip equality (`NaN != NaN`
    makes `needs_upgrade`/idempotency checks oscillate) and serialises to the non-reloadable cell
    `"nan"`; an authored measure is always a finite number. Passes `None` through."""
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{field_name} must be a finite number, got: {value!r}")
    return value
