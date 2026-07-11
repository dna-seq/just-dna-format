"""
The measure → phenotype binning primitive (0.4 — PROPOSAL_0_4 §B0/T1/T3).

One declarative shape shared by every quantity-carrying locus: a per-locus table that maps a
*measured quantity* (activity score, copy number, repeat count, heteroplasmy fraction, PRS
percentile) to a phenotype by range. The tables differ only in **which** quantity is measured and
in their explicit key columns (multicolumn keying — never a packed tuple, PROPOSAL_0_4 keying
stance). Aligning the column vocabulary gives a consumer one "bin-a-measure" code path.

**Data-agnostic (design north star — see CLAUDE.md).** These rows are pure annotation: a lookup
table declaring range→phenotype. The module contains **no measurement** — the measured quantity is
supplied by the consumer at query time; the table never sees a sample. The bins themselves are a
generalization over a practical subset of real loci/ranges, not an all-encompassing model, so a data
item that doesn't fit is a schema gap to widen additively.

**Ranges are inclusive `[measure_min, measure_max]`**: `min == max` is a *sharp* value (e.g. exactly
0 copies), `min < max` is a range (HTT 36–39 CAG), and `measure_max = None` is open-ended (≥40 CAG,
3+ copies). There is no `copy_number` column — a sharp copy number is `measure_min == measure_max`.

**`unresolved` (T1) is mandatory.** A table can state the outcome for *measurement absent / not
callable*, and the consumer contract is that a missing measurement selects the `unresolved` row,
**never the lowest/reference bin** (no activity score ⇒ not "Normal Metabolizer"; no CN ⇒ not "2
copies"; no heteroplasmy read ⇒ not "homoplasmic reference"). An `unresolved` row carries no bounds.
A measurement that is *present but matches no bin* is a distinct third state ("no matching bin", not
`unresolved`); `validate_bins` below rejects overlaps and flags coverage gaps so a table stays
coherent (consumer round-2 C1).

**`source_field` (round-2 3a) is a declarative *pointer*, not code.** It optionally names the VCF
`FORMAT`/`INFO` field the consumer extracts the measure from (`REPCN`, `AF`, `CN|DS`) — pure
indirection/addressing, deliberately constrained to a bare field-name token (optionally `|`-alternated)
so it can never become an expression. That keeps it inside Principle 1 (declarative, non-Turing): a
name that says *where the measurement lives*, never a transform that computes one. The module still
holds no measurement.
"""

import math
import re
from collections import defaultdict
from typing import ClassVar, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from just_dna_format.vocab import (
    VALID_CLIN_SIG,
    VALID_DIRECTIONS,
    check_vocab,
    validate_finite,
    validate_trait_ids,
)

# Open, additive vocabulary of measured quantities (the `frozenset[str]` idiom, Principle 6). New
# quantities are added in a future release; unknown values are rejected (closed-validated).
VALID_MEASURE_KINDS: frozenset[str] = frozenset(
    {"activity_score", "copy_number", "repeat_count", "allele_fraction", "prs_percentile"}
)

# A `source_field` is one VCF field-name token, optionally `|`-alternated (`CN|DS`). This grammar is
# what keeps the binding a *pointer* and not an expression — no operators, no whitespace, no code.
SOURCE_FIELD_PATTERN: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\|[A-Za-z_][A-Za-z0-9_]*)*$")

# Which measure kinds have a meaningful numeric coverage gap. Integer counts are contiguous when
# bins are adjacent (`[27,35]`,`[36,39]`); truly continuous fractions are not. `activity_score` is a
# consumer-summed quantized quantity, so interior "gaps" are not meaningful — excluded.
_INTEGER_KINDS: frozenset[str] = frozenset({"repeat_count", "copy_number"})
_CONTINUOUS_GAP_KINDS: frozenset[str] = frozenset({"allele_fraction", "prs_percentile"})


class MeasureBinRow(BaseModel):
    """Base row of a binning table: a measured quantity range → the same orthogonal axes a
    `VariantRow` carries. Subclasses add the explicit key columns for their quantity.

    `extra="forbid"` is the reserved-namespace boundary — a column named for a not-yet-built
    reserved field (`caller`, `requires_callable`, `actionability`, …) is rejected until a release
    claims it.
    """

    model_config = ConfigDict(extra="forbid")

    # Subclasses pin their measure_kind via this ClassVar (see `_validate_measure_kind`).
    _EXPECTED_KIND: ClassVar[Optional[str]] = None
    # The explicit key columns for this quantity (used by `validate_bins` to group rows). The unit
    # is part of the key (T3): a measurement is only comparable within its motif/reference/modifier.
    _KEY_FIELDS: ClassVar[tuple[str, ...]] = ()

    measure_kind: str = Field(description="Measured quantity; one of VALID_MEASURE_KINDS")
    measure_min: Optional[float] = Field(
        default=None, description="Inclusive lower bound; None = open below"
    )
    measure_max: Optional[float] = Field(
        default=None, description="Inclusive upper bound; None = open above"
    )
    direction: Optional[str] = Field(
        default=None, description="Effect direction: protective|risk|neutral|unknown"
    )
    clin_sig: Optional[str] = Field(
        default=None, description="ClinVar/ACMG clinical significance (VEP CLIN_SIG vocabulary)"
    )
    phenotype: Optional[str] = Field(default=None, description="Associated trait or phenotype")
    trait_efo_id: Optional[str] = Field(
        default=None, description="EFO/MONDO/OBA/HP trait ontology id(s)"
    )
    conclusion: str = Field(description="Human-readable interpretation for this bin")
    unresolved: bool = Field(
        default=False,
        description="True on the sentinel row a consumer selects when the measurement is absent.",
    )
    source_field: Optional[str] = Field(
        default=None,
        description=(
            "Optional VCF FORMAT/INFO field the consumer extracts this measure from (e.g. REPCN, "
            "AF, CN|DS). A declarative pointer (bare field-name token, optionally |-alternated), "
            "never an expression — an extraction hint; the measurement still comes from the consumer."
        ),
    )

    @field_validator("source_field")
    @classmethod
    def _validate_source_field(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not SOURCE_FIELD_PATTERN.match(v):
            raise ValueError(
                f"source_field must be a bare VCF field-name token, optionally |-alternated "
                f"(e.g. REPCN, CN|DS) — a pointer, not an expression, got: {v!r}"
            )
        return v

    @field_validator("measure_min", "measure_max")
    @classmethod
    def _validate_bound_finite(cls, v: Optional[float]) -> Optional[float]:
        return validate_finite(v, "measure bound")

    @field_validator("measure_kind")
    @classmethod
    def _validate_measure_kind(cls, v: str) -> str:
        check_vocab(v, VALID_MEASURE_KINDS, "measure_kind")
        expected = cls._EXPECTED_KIND
        if expected is not None and v != expected:
            raise ValueError(f"{cls.__name__} requires measure_kind={expected!r}, got: {v!r}")
        return v

    @field_validator("direction")
    @classmethod
    def _validate_direction(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_DIRECTIONS, "direction")

    @field_validator("clin_sig")
    @classmethod
    def _validate_clin_sig(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_CLIN_SIG, "clin_sig")

    @field_validator("trait_efo_id")
    @classmethod
    def _validate_trait_efo_id(cls, v: Optional[str]) -> Optional[str]:
        return validate_trait_ids(v)

    @model_validator(mode="after")
    def _validate_range(self) -> "MeasureBinRow":
        if self.unresolved:
            if self.measure_min is not None or self.measure_max is not None:
                raise ValueError(
                    "an unresolved row carries no measure_min/measure_max (it is the sentinel a "
                    "consumer selects when no measurement is available)"
                )
            return self
        if self.measure_min is None and self.measure_max is None:
            raise ValueError(
                "a resolved bin needs at least one of measure_min/measure_max "
                "(set unresolved=True for the measurement-absent sentinel)"
            )
        if (
            self.measure_min is not None
            and self.measure_max is not None
            and self.measure_min > self.measure_max
        ):
            raise ValueError(
                f"measure_min must be <= measure_max (min == max is a sharp value), got "
                f"[{self.measure_min}, {self.measure_max}]"
            )
        return self


class ActivityPhenotypeRow(MeasureBinRow):
    """PGx metabolizer phenotype by activity score, per gene (CYP2D6 PM/IM/NM/UM). The score is a
    consumer call (Σ activity×copies over the diplotype); this table only bins it."""

    _EXPECTED_KIND: ClassVar[str] = "activity_score"
    _KEY_FIELDS: ClassVar[tuple[str, ...]] = ("gene",)

    gene: str = Field(description="Gene symbol, e.g. CYP2D6")
    measure_kind: str = Field(default="activity_score", description="Fixed: activity_score")


class CopyNumberRow(MeasureBinRow):
    """Whole-gene dosage phenotype by copy number (SMN1 SMA). Sharp dosages are
    `measure_min == measure_max` (0 copies = [0, 0]); `3+` is `measure_min=3, measure_max=None`.

    Optional `modifier_gene`/`modifier_cn` express a second dosage locus read in context (SMN1
    phenotype depends on SMN2 copy number) — explicit named columns (multicolumn keying), never a
    tuple. Both are set together or both left null.
    """

    _EXPECTED_KIND: ClassVar[str] = "copy_number"
    # The modifier is part of the key: SMN1=0 with SMN2=3 vs SMN2=1 are distinct bins, not an overlap.
    _KEY_FIELDS: ClassVar[tuple[str, ...]] = ("gene", "modifier_gene", "modifier_cn")

    gene: str = Field(description="Gene symbol whose copy number is binned, e.g. SMN1")
    modifier_gene: Optional[str] = Field(
        default=None, description="Optional modifier locus read in context, e.g. SMN2"
    )
    modifier_cn: Optional[int] = Field(
        default=None, description="Copy number of the modifier locus (set with modifier_gene)"
    )
    measure_kind: str = Field(default="copy_number", description="Fixed: copy_number")

    @model_validator(mode="after")
    def _validate_modifier(self) -> "CopyNumberRow":
        if (self.modifier_gene is None) != (self.modifier_cn is None):
            raise ValueError(
                "modifier_gene and modifier_cn are set together or both left null, got "
                f"modifier_gene={self.modifier_gene!r}, modifier_cn={self.modifier_cn!r}"
            )
        return self


class RepeatAlleleRow(MeasureBinRow):
    """VNTR/STR phenotype by repeat count, keyed on `(gene, repeat_unit)` — the motif is part of
    the identity (T3): a count is only comparable within its motif definition. The count is a
    consumer call (ExpansionHunter / adVNTR / a span genotyper) that MUST state the motif it
    counted."""

    _EXPECTED_KIND: ClassVar[str] = "repeat_count"
    _KEY_FIELDS: ClassVar[tuple[str, ...]] = ("gene", "repeat_unit")

    gene: str = Field(description="Gene symbol, e.g. HTT")
    repeat_unit: str = Field(description="Repeat motif, part of the key, e.g. CAG")
    measure_kind: str = Field(default="repeat_count", description="Fixed: repeat_count")


# The known-dangerous legacy mtDNA reference lineage: NC_001807 silently disagrees with rCRS
# (NC_012920) coordinates and bases, yielding a *confidently-wrong* haplogroup (consumer round-2 Q3).
# Not a closed allow-list (future refs exist) — the validator rejects only this enumerated landmine.
LEGACY_MT_REFERENCE_BASES: frozenset[str] = frozenset({"NC_001807"})
CANONICAL_MT_REFERENCE_SEQUENCES: frozenset[str] = frozenset({"NC_012920.1"})


class HeteroplasmyRow(MeasureBinRow):
    """mtDNA phenotype by heteroplasmy allele fraction (0–1), keyed on
    `(gene, reference_sequence, tissue)`. The reference sequence is part of the key (A3): rCRS/
    NC_012920 vs legacy NC_001807 disagree and `genome_build` does not disambiguate. Bounds are
    constrained to `[0, 1]`.

    `tissue`/`assay_context` are optional but load-bearing (round-2 Q6): heteroplasmy bins are
    **tissue-conditional** — a blood-derived fraction systematically under-represents the
    affected-tissue burden, and the penetrance threshold itself shifts by tissue, so the *same*
    fraction bins to different phenotypes across tissues. A heteroplasmy table with no tissue context
    is quietly unsafe; state the tissue the bins assume."""

    _EXPECTED_KIND: ClassVar[str] = "allele_fraction"
    _KEY_FIELDS: ClassVar[tuple[str, ...]] = ("gene", "reference_sequence", "tissue")

    gene: str = Field(description="MT locus/gene, e.g. MT-TL1")
    reference_sequence: str = Field(
        description="MT reference accession, part of the key, e.g. NC_012920.1 (rCRS)"
    )
    tissue: Optional[str] = Field(
        default=None, description="Tissue the bins assume, e.g. blood, muscle (bins are tissue-conditional)"
    )
    assay_context: Optional[str] = Field(
        default=None, description="Optional assay context, e.g. WGS, chip, amplicon"
    )
    measure_kind: str = Field(default="allele_fraction", description="Fixed: allele_fraction")

    @field_validator("reference_sequence")
    @classmethod
    def _reject_legacy_reference(cls, v: str) -> str:
        if v.split(".")[0] in LEGACY_MT_REFERENCE_BASES:
            raise ValueError(
                f"reference_sequence {v!r} is the legacy NC_001807 lineage, which disagrees with "
                f"rCRS (NC_012920) coordinates/bases and yields a confidently-wrong haplogroup; "
                f"use NC_012920.1"
            )
        return v

    @model_validator(mode="after")
    def _validate_fraction_bounds(self) -> "HeteroplasmyRow":
        for bound in (self.measure_min, self.measure_max):
            if bound is not None and not (0.0 <= bound <= 1.0):
                raise ValueError(
                    f"allele_fraction bounds must be within [0, 1], got {bound}"
                )
        return self


def validate_bins(rows: Sequence[MeasureBinRow]) -> list[str]:
    """Table-level coherence check for a set of binning rows of one kind (consumer round-2 C1).

    Rows are grouped by their explicit key columns (`_KEY_FIELDS`) plus `trait_efo_id`. Within a
    group of *resolved* rows — a consumer measurement selects at most one — inclusive ranges
    `[measure_min, measure_max]` (a null bound = -inf/+inf) **must not overlap**; an overlap would
    select two phenotypes for one measurement and raises ``ValueError``. Overlap *across* different
    `trait_efo_id` is allowed (pleiotropy — the same measurement legitimately binning to two traits).
    `unresolved` sentinel rows carry no range and are ignored.

    Returns a list of **warnings** for interior coverage gaps (a value between two authored bins that
    matches no row): for integer kinds a hole spanning ≥1 uncovered integer, for continuous fractions
    any positive hole. `activity_score` is consumer-summed/quantized, so interior gaps are not
    meaningful and are not flagged. Edge coverage *below* the lowest bin (the "author the reference
    bin" contract, C1) is a consumer-contract matter, not auto-detected here — it would false-positive
    without a known domain floor. Callers decide what to do with the warnings (log, fail, ignore).
    """
    warnings: list[str] = []
    groups: dict[tuple, list[MeasureBinRow]] = defaultdict(list)
    for r in rows:
        if r.unresolved:
            continue
        group_key = tuple(getattr(r, f, None) for f in r._KEY_FIELDS) + (r.trait_efo_id,)
        groups[group_key].append(r)

    for group_key, grp in groups.items():
        spans = sorted(
            (
                (
                    -math.inf if r.measure_min is None else r.measure_min,
                    math.inf if r.measure_max is None else r.measure_max,
                )
                for r in grp
            ),
            key=lambda t: (t[0], t[1]),
        )
        kind = grp[0].measure_kind
        for i in range(1, len(spans)):
            prev_lo, prev_hi = spans[i - 1]
            lo, hi = spans[i]
            if lo <= prev_hi:  # inclusive overlap
                raise ValueError(
                    f"overlapping bins for key {group_key}: [{prev_lo}, {prev_hi}] and "
                    f"[{lo}, {hi}] both select a phenotype for a measurement in the overlap"
                )
            hole = lo - prev_hi
            is_gap = (kind in _INTEGER_KINDS and hole > 1 + 1e-9) or (
                kind in _CONTINUOUS_GAP_KINDS and hole > 1e-9
            )
            if is_gap:
                warnings.append(
                    f"coverage gap for key {group_key}: no bin covers ({prev_hi}, {lo})"
                )
    return warnings
