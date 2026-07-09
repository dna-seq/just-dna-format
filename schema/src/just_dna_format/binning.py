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
"""

from typing import ClassVar, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from just_dna_format.vocab import (
    VALID_CLIN_SIG,
    VALID_DIRECTIONS,
    check_vocab,
    validate_trait_ids,
)

# Open, additive vocabulary of measured quantities (the `frozenset[str]` idiom, Principle 6). New
# quantities are added in a future release; unknown values are rejected (closed-validated).
VALID_MEASURE_KINDS: frozenset[str] = frozenset(
    {"activity_score", "copy_number", "repeat_count", "allele_fraction", "prs_percentile"}
)


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

    gene: str = Field(description="Gene symbol, e.g. HTT")
    repeat_unit: str = Field(description="Repeat motif, part of the key, e.g. CAG")
    measure_kind: str = Field(default="repeat_count", description="Fixed: repeat_count")


class HeteroplasmyRow(MeasureBinRow):
    """mtDNA phenotype by heteroplasmy allele fraction (0–1), keyed on `(gene, reference_sequence)`.
    The reference sequence is part of the key (A3): rCRS/NC_012920 vs legacy NC_001807 disagree and
    `genome_build` does not disambiguate. Bounds are constrained to `[0, 1]`."""

    _EXPECTED_KIND: ClassVar[str] = "allele_fraction"

    gene: str = Field(description="MT locus/gene, e.g. MT-TL1")
    reference_sequence: str = Field(
        description="MT reference accession, part of the key, e.g. NC_012920.1 (rCRS)"
    )
    measure_kind: str = Field(default="allele_fraction", description="Fixed: allele_fraction")

    @model_validator(mode="after")
    def _validate_fraction_bounds(self) -> "HeteroplasmyRow":
        for bound in (self.measure_min, self.measure_max):
            if bound is not None and not (0.0 <= bound <= 1.0):
                raise ValueError(
                    f"allele_fraction bounds must be within [0, 1], got {bound}"
                )
        return self
