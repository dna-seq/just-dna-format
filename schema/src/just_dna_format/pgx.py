"""
PGx star-allele model (0.4 — PROPOSAL_0_4 §B1). Three definition/lookup tables that, with the
per-gene `ActivityPhenotypeRow` binning table (`binning.py`), form the four-table model validated
against the Aldy / Cyrius / PharmCAT stack:

1. `HaplotypeRow`      — junction: variant ↔ allele is many-to-many (one allele = many variants;
                         one variant recurs across many alleles). One row per (haplotype × variant).
2. `AlleleFunctionRow` — allele-unit → activity value + function category. The **star-string is the
                         canonical identity, stored verbatim** (`*4`, `*1x2`, `*36+*10`); copy
                         number / SV are attributes of the *cis* allele-unit, optional parsed
                         conveniences (the string is truth — PharmVar has no structured SV field).
3. `DiplotypeRow`      — the safe canonical fallback for structural/duplication/unphased cases,
                         keyed on a canonicalized haplotype pair.

Data-agnostic (design north star — see CLAUDE.md): the format supplies these tables; a **consumer**
star-allele caller supplies the phased diplotype + CN/SV calls and computes the phenotype. Copy number attaches
to a specific *cis* allele-unit, so `*2x2/*4` (AS 2 → NM) ≠ `*2/*4x2` (AS 1 → IM) — a consumer that
multiplies by *total* CN gets it wrong.
"""

import re
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from just_dna_format.vocab import (
    VALID_CLIN_SIG,
    VALID_DIRECTIONS,
    VALID_EVIDENCE_LEVELS,
    check_vocab,
    validate_allele,
    validate_rsid,
    validate_trait_ids,
)

# Star-allele string, stored verbatim as the canonical identity. Permissive by design (the string
# is truth): a leading `*` then digits/letters and the sub-allele/duplication/tandem punctuation
# PharmVar uses (`.`, `+`, `x`/`×`), e.g. `*4`, `*4.001`, `*1x2`, `*36+*10`.
STAR_ALLELE_PATTERN: re.Pattern[str] = re.compile(r"^\*[0-9A-Za-z][0-9A-Za-z.\-+x×*]*$")
# CPIC/PharmVar allele function categories (closed vocabulary, Principle 6).
VALID_FUNCTION_STATUS: frozenset[str] = frozenset(
    {
        "no_function",
        "decreased_function",
        "normal_function",
        "increased_function",
        "uncertain_function",
        "unknown_function",
    }
)


class HaplotypeRow(BaseModel):
    """Junction row: one defining variant of a named haplotype/allele. Many rows per haplotype;
    a variant recurs across many haplotypes (CYP2D6 rs1065852 is core-defining in 22 alleles)."""

    model_config = ConfigDict(extra="forbid")

    haplotype_name: str = Field(description="Named haplotype/allele, e.g. *4 or e4")
    rsid: Optional[str] = Field(default=None, description="dbSNP id of the defining variant")
    chrom: Optional[str] = Field(default=None, description="Chromosome (position-only variants)")
    start: Optional[int] = Field(default=None, description="0-based position (position-only)")
    ref: Optional[str] = Field(default=None, description="Reference allele (position-only)")
    allele: str = Field(description="The defining (variant) allele on this haplotype, nucleotides")
    gene: Optional[str] = Field(default=None, description="Gene symbol, e.g. CYP2D6")

    @field_validator("rsid")
    @classmethod
    def _validate_rsid(cls, v: Optional[str]) -> Optional[str]:
        return validate_rsid(v)

    @field_validator("allele")
    @classmethod
    def _validate_allele(cls, v: str) -> str:
        return validate_allele(v, "allele") or v

    @model_validator(mode="after")
    def _validate_identification(self) -> "HaplotypeRow":
        if self.rsid is None and (self.chrom is None or self.start is None):
            raise ValueError(
                "a haplotype variant needs an identifier: rsid, or chrom + start"
            )
        return self


class AlleleFunctionRow(BaseModel):
    """Allele-unit → activity value + function category. The star-string `allele` is the required
    canonical key. `suballele` is optional-extra (Aldy's `Minor`, e.g. 1.001); the core star is the
    identity. `copy_number`/`sv_type`/`hybrid_orientation` are optional parsed conveniences of the
    *cis* allele-unit — the star-string remains truth."""

    model_config = ConfigDict(extra="forbid")

    gene: str = Field(description="Gene symbol, e.g. CYP2D6")
    allele: str = Field(description="Star-allele string, verbatim canonical identity, e.g. *4")
    activity_value: Optional[float] = Field(
        default=None, description="Per-allele activity value (e.g. *1=1.0, *10=0.25, *4=0)"
    )
    function_status: Optional[str] = Field(
        default=None, description="CPIC function category (VALID_FUNCTION_STATUS)"
    )
    suballele: Optional[str] = Field(
        default=None, description="Optional finer sub-allele, e.g. 1.001 (core star is the key)"
    )
    copy_number: Optional[int] = Field(
        default=None, description="Optional cis copy number of the allele-unit (e.g. *1x2 → 2)"
    )
    sv_type: Optional[str] = Field(
        default=None, description="Optional parsed SV type (duplication/deletion/hybrid)"
    )
    hybrid_orientation: Optional[str] = Field(
        default=None, description="Optional parsed tandem/hybrid orientation, e.g. *36+*10"
    )

    @field_validator("allele")
    @classmethod
    def _validate_allele(cls, v: str) -> str:
        if not STAR_ALLELE_PATTERN.match(v):
            raise ValueError(f"allele must be a star-allele string like *4 or *36+*10, got: {v!r}")
        return v

    @field_validator("function_status")
    @classmethod
    def _validate_function_status(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_FUNCTION_STATUS, "function_status")


class DiplotypeRow(BaseModel):
    """Canonical fallback: a diplotype (haplotype pair) → phenotype. The pair is canonicalized
    (`haplotype_a <= haplotype_b`) so a lookup is order-independent; multiple rows per pair are
    allowed (a pleiotropic diplotype affecting several traits)."""

    model_config = ConfigDict(extra="forbid")

    gene: str = Field(description="Gene symbol, e.g. CYP2D6")
    haplotype_a: str = Field(description="First haplotype of the pair (canonicalized a <= b)")
    haplotype_b: str = Field(description="Second haplotype of the pair")
    trait_efo_id: Optional[str] = Field(
        default=None, description="EFO/MONDO/OBA/HP trait ontology id(s)"
    )
    direction: Optional[str] = Field(default=None, description="Effect direction")
    clin_sig: Optional[str] = Field(default=None, description="Clinical significance")
    phenotype: Optional[str] = Field(default=None, description="Metabolizer phenotype, e.g. PM/NM")
    conclusion: str = Field(description="Human-readable interpretation for this diplotype")

    # ── Optional PharmGKB drug context (item 9) — a diplotype → drug response. Diplotype-keyed, so it
    # rides here; single-variant drug response lives in the separate PharmVariantRow. ──
    drug: Optional[str] = Field(default=None, description="Drug the response is about, e.g. codeine")
    response: Optional[str] = Field(default=None, description="Drug response / phenotype, free-form")
    evidence_level: Optional[str] = Field(
        default=None, description="PharmGKB clinical-annotation evidence level (1A..4)"
    )

    @field_validator("direction")
    @classmethod
    def _validate_direction(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_DIRECTIONS, "direction")

    @field_validator("clin_sig")
    @classmethod
    def _validate_clin_sig(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_CLIN_SIG, "clin_sig")

    @field_validator("evidence_level")
    @classmethod
    def _validate_evidence_level(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_EVIDENCE_LEVELS, "evidence_level")

    @field_validator("trait_efo_id")
    @classmethod
    def _validate_trait_efo_id(cls, v: Optional[str]) -> Optional[str]:
        return validate_trait_ids(v)

    @model_validator(mode="after")
    def _canonicalize_pair(self) -> "DiplotypeRow":
        # Order-independent key: store the lexicographically smaller haplotype first, so a lookup
        # of (a, b) and (b, a) hit the same row.
        if self.haplotype_a > self.haplotype_b:
            self.haplotype_a, self.haplotype_b = self.haplotype_b, self.haplotype_a
        return self


class PharmVariantRow(BaseModel):
    """Single-variant PharmGKB drug-response annotation (item 9) — `pharm_variants.csv`.

    A **distinct rowtype** rather than columns on `VariantRow`, so the SNP core stays free of the
    drug-response domain: a module includes this table only when it carries drug annotations (one CSV
    = one concern; no empty `variants.csv`). Diplotype-keyed drug response instead rides on
    `DiplotypeRow`'s optional drug columns. A row maps a variant → a **drug** → a **response** +
    a PharmGKB **evidence level** (1A…4) — a different axis from a risk weight (why it is not a
    `VariantRow`)."""

    model_config = ConfigDict(extra="forbid")

    rsid: Optional[str] = Field(default=None, description="dbSNP id of the variant, e.g. rs9923231")
    chrom: Optional[str] = Field(default=None, description="Chromosome (position-only variants)")
    start: Optional[int] = Field(default=None, description="0-based position (position-only)")
    ref: Optional[str] = Field(default=None, description="Reference allele (position-only)")
    gene: Optional[str] = Field(default=None, description="Gene symbol, e.g. VKORC1")
    drug: str = Field(description="Drug the response annotation is about, e.g. warfarin")
    response: Optional[str] = Field(
        default=None, description="Drug response / phenotype, free-form (e.g. 'reduced dose requirement')"
    )
    evidence_level: Optional[str] = Field(
        default=None, description="PharmGKB clinical-annotation evidence level (1A..4)"
    )
    trait_efo_id: Optional[str] = Field(
        default=None, description="Optional trait ontology id(s), for cross-module join"
    )
    conclusion: str = Field(description="Human-readable interpretation")

    @property
    def variant_key(self) -> str:
        """Stable key matching VariantRow.variant_key."""
        if self.rsid is not None:
            return self.rsid
        return f"{self.chrom}:{self.start}:{self.ref}"

    @field_validator("rsid")
    @classmethod
    def _validate_rsid(cls, v: Optional[str]) -> Optional[str]:
        return validate_rsid(v)

    @field_validator("evidence_level")
    @classmethod
    def _validate_evidence_level(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_EVIDENCE_LEVELS, "evidence_level")

    @field_validator("trait_efo_id")
    @classmethod
    def _validate_trait_efo_id(cls, v: Optional[str]) -> Optional[str]:
        return validate_trait_ids(v)

    @model_validator(mode="after")
    def _validate_identification(self) -> "PharmVariantRow":
        if self.rsid is None and (self.chrom is None or self.start is None):
            raise ValueError("a pharm variant needs an identifier: rsid, or chrom + start")
        return self
