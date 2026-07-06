"""
The authored module spec DSL (`module_spec.yaml` + `variants.csv` + `studies.csv`).

This is the *input* half of the module format; `manifest.py` is the *output* half. Both live in
this dependency-light package so the compiler is a pure transform between two validated schema
sets, and any consumer can validate a spec or a manifest without pulling the compiler's polars/
duckdb weight.

Identity/display rules reuse the shared helpers in `identity` and `manifest`, so the DSL and the
manifest enforce exactly the same constraints.
"""

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from just_dna_format.identity import validate_name
from just_dna_format.manifest import SCHEMA_VERSION, Display

VALID_STATES: frozenset[str] = frozenset(
    {"risk", "protective", "neutral", "significant", "alt", "ref"}
)
VALID_CHROMOSOMES: frozenset[str] = frozenset(
    {str(i) for i in range(1, 23)} | {"X", "Y", "MT"}
)
RSID_PATTERN: re.Pattern[str] = re.compile(r"^rs\d+$")
ALLELE_PATTERN: re.Pattern[str] = re.compile(r"^[ACGT]+$", re.IGNORECASE)


class ModuleInfo(Display):
    """The `module:` block of module_spec.yaml: a machine `name` plus the shared `Display`
    metadata (title/description/report_title/icon/color).

    Extends the manifest's `Display` rather than re-declaring those fields, so the display schema
    and its validation (e.g. the hex-colour rule) live in exactly one place. `name` lives here on
    the authoring side; the manifest routes it into `Identity` instead.
    """

    name: str = Field(description="Machine name: lowercase, underscores, no spaces")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        return validate_name(v)


class Defaults(BaseModel):
    """Default values applied to variant rows when not explicitly set."""

    curator: str = Field(default="ai-module-creator", description="Default curator identifier")
    method: str = Field(default="literature-review", description="Default annotation method")
    priority: Optional[str] = Field(default=None, description="Default priority level")


class ModuleSpecConfig(BaseModel):
    """Top-level model for module_spec.yaml."""

    schema_version: str = Field(default=SCHEMA_VERSION, description="DSL schema version")
    module: ModuleInfo = Field(description="Module identity and display metadata")
    defaults: Defaults = Field(default_factory=Defaults, description="Default variant-row values")
    genome_build: str = Field(default="GRCh38", description="Reference genome build for positions")

    @field_validator("schema_version")
    @classmethod
    def _validate_version(cls, v: str) -> str:
        if v != SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema_version: {v!r}. Expected {SCHEMA_VERSION!r}")
        return v


class VariantRow(BaseModel):
    """One row of variants.csv. At least one identifier (rsid or chrom+start) is required."""

    rsid: Optional[str] = Field(default=None, description="dbSNP identifier, e.g. rs1801133")
    chrom: Optional[str] = Field(default=None, description="Chromosome without 'chr' prefix")
    start: Optional[int] = Field(default=None, description="0-based genomic position (GRCh38)")
    ref: Optional[str] = Field(default=None, description="Reference allele")
    alts: Optional[str] = Field(default=None, description="Alt allele(s), comma-separated")
    genotype: str = Field(description="Slash-separated sorted alleles, e.g. A/G")
    weight: Optional[float] = Field(default=None, description="Score (positive=protective)")
    state: str = Field(description="One of: risk, protective, neutral, significant, alt, ref")
    conclusion: str = Field(description="Human-readable interpretation for this genotype")
    priority: Optional[str] = Field(default=None, description="Priority level override")
    gene: Optional[str] = Field(default=None, description="Gene symbol, e.g. MTHFR")
    phenotype: Optional[str] = Field(default=None, description="Associated trait or phenotype")
    category: Optional[str] = Field(default=None, description="Grouping category within the module")
    clinvar: Optional[bool] = Field(default=None, description="Is this variant in ClinVar?")
    pathogenic: Optional[bool] = Field(default=None, description="ClinVar pathogenic flag")
    benign: Optional[bool] = Field(default=None, description="ClinVar benign flag")
    curator: Optional[str] = Field(default=None, description="Curator override")
    method: Optional[str] = Field(default=None, description="Annotation method override")

    @property
    def variant_key(self) -> str:
        """Stable grouping key: rsid when available, else chrom:start:ref."""
        if self.rsid is not None:
            return self.rsid
        return f"{self.chrom}:{self.start}:{self.ref}"

    @field_validator("rsid")
    @classmethod
    def _validate_rsid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not RSID_PATTERN.match(v):
            raise ValueError(f"rsid must match rs<digits>, got: {v!r}")
        return v

    @field_validator("state")
    @classmethod
    def _validate_state(cls, v: str) -> str:
        if v not in VALID_STATES:
            raise ValueError(f"state must be one of {sorted(VALID_STATES)}, got: {v!r}")
        return v

    @field_validator("chrom")
    @classmethod
    def _validate_chrom(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            normalized = v.removeprefix("chr")
            if normalized not in VALID_CHROMOSOMES:
                raise ValueError(
                    f"chrom must be one of 1-22, X, Y, MT (without 'chr' prefix), got: {v!r}"
                )
            return normalized
        return v

    @field_validator("genotype")
    @classmethod
    def _validate_genotype(cls, v: str) -> str:
        parts = v.split("/")
        if len(parts) != 2:
            raise ValueError(f"genotype must be two alleles slash-separated (e.g. A/G), got: {v!r}")
        for allele in parts:
            if not ALLELE_PATTERN.match(allele):
                raise ValueError(
                    f"genotype alleles must be uppercase nucleotides, got: {allele!r} in {v!r}"
                )
        if parts != sorted(parts):
            raise ValueError(
                f"genotype alleles must be alphabetically sorted: "
                f"expected {'/'.join(sorted(parts))!r}, got: {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _validate_identification(self) -> "VariantRow":
        has_rsid = self.rsid is not None
        positional = {"chrom": self.chrom, "start": self.start}
        has_pos = any(v is not None for v in positional.values())
        has_ref = any(v is not None for v in {"ref": self.ref, "alts": self.alts}.values())

        if not has_rsid and not has_pos:
            raise ValueError(
                "At least one identifier is required: provide rsid or position (chrom + start)"
            )
        if has_pos:
            missing = [k for k, v in positional.items() if v is None]
            if missing:
                raise ValueError(
                    f"If any positional columns are provided, chrom and start are required. "
                    f"Missing: {missing}"
                )
        if has_ref and not has_pos:
            raise ValueError("ref/alts require chrom and start to also be provided")
        return self


class StudyRow(BaseModel):
    """One row of studies.csv: an (rsid, pmid) evidence link. Grounding evidence is mandatory."""

    rsid: Optional[str] = Field(default=None, description="dbSNP identifier or variant key")
    chrom: Optional[str] = Field(default=None, description="Chromosome (for position-only variants)")
    start: Optional[int] = Field(default=None, description="0-based position (position-only variants)")
    ref: Optional[str] = Field(default=None, description="Reference allele (position-only variants)")
    pmid: str = Field(description="PubMed ID or reference — free-form, must be non-empty")
    population: Optional[str] = Field(default=None, description="Study population")
    p_value: Optional[str] = Field(default=None, description="Statistical significance")
    conclusion: Optional[str] = Field(default=None, description="Study-specific conclusion")
    study_design: Optional[str] = Field(default=None, description="e.g. meta-analysis, GWAS")

    @property
    def variant_key(self) -> str:
        """Stable key matching VariantRow.variant_key."""
        if self.rsid is not None:
            return self.rsid
        return f"{self.chrom}:{self.start}:{self.ref}"

    @field_validator("rsid")
    @classmethod
    def _validate_rsid(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not RSID_PATTERN.match(v):
            raise ValueError(f"rsid must match rs<digits>, got: {v!r}")
        return v

    @field_validator("pmid")
    @classmethod
    def _validate_pmid(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("pmid must not be empty")
        return v

    @model_validator(mode="after")
    def _validate_study_identification(self) -> "StudyRow":
        if self.rsid is None and self.chrom is None:
            raise ValueError(
                "At least one identifier is required: provide rsid or position (chrom + start)"
            )
        return self
