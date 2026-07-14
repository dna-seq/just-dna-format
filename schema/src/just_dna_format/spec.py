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

from just_dna_format.derive import (
    benign_from_clin_sig,
    clin_sig_from_booleans,
    direction_from_state,
    pathogenic_from_clin_sig,
    stat_significance_from_state,
    trimmed_state,
)
from just_dna_format.identity import validate_name
from just_dna_format.manifest import SCHEMA_VERSION, Contribution, Display, GenePanelSpec
from just_dna_format.vocab import (
    ACTIONABILITY_SEED,
    ALLELE_PATTERN,
    VALID_CLIN_SIG,
    VALID_DIRECTIONS,
    VALID_SIGNIFICANCE,
    check_vocab,
    validate_allele,
    validate_finite,
    validate_rsid,
    validate_trait_ids,
)
from just_dna_format.vocab import MULTI_SEP as _MULTI_SEP

# The orthogonal-axis vocabularies and identifier grammars now live in `vocab` (shared across the
# authored models). `VALID_DIRECTIONS`/`VALID_SIGNIFICANCE`/`VALID_CLIN_SIG` (and `ALLELE_PATTERN`)
# are re-exported here for backward compatibility. Spec-only vocabularies stay below.
VALID_STATES: frozenset[str] = frozenset(
    {"risk", "protective", "neutral", "significant", "alt", "ref"}
)
VALID_CHROMOSOMES: frozenset[str] = frozenset(
    {str(i) for i in range(1, 23)} | {"X", "Y", "MT"}
)
# `flags` is an OPEN list. These are the reserved tags the tooling acts on; any other tag is
# accepted and surfaced as INFO (not a warning) by the compiler. Never put direction / clinical
# / consequence / drug words here — those have (or get) typed columns.
RESERVED_FLAGS: frozenset[str] = frozenset({"conditional", "phased", "pleiotropic"})
# `effect_measure` is intentionally NOT a closed vocabulary (kept permissive so PGS-Catalog
# `weight_type` additions survive). These are the recommended values, for documentation only.
RECOMMENDED_EFFECT_MEASURES: frozenset[str] = frozenset(
    {"OR", "HR", "RR", "beta", "log(OR)", "log(HR)", "NR"}
)
# A PMID is a run of digits. Real sources present them bare (`9545397`), bracketed/prefixed
# (`[PMID: 9545397]`), or as a `;`-joined list (`PMID 17478681; PMID: 30278588`). We accept any
# string that carries at least one PMID token and keep it verbatim (ROADMAP item 6 / Obs #4).
PMID_PATTERN: re.Pattern[str] = re.compile(r"\b(\d{1,8})\b")
# A DOI is `10.<registrant>/<suffix>` (Crockford/Handle grammar). Real sources present it bare
# (`10.1234/abc.def`) or wrapped in a URL (`https://doi.org/10.1234/abc`); we accept any string that
# carries one DOI token and keep it verbatim, mirroring the PMID contract. Wider than a PMID: it also
# covers preprints/books/datasets with no PubMed id (docs/USE_CASES.md §4a, RM11).
DOI_PATTERN: re.Pattern[str] = re.compile(r"10\.\d{4,9}/\S+")


def extract_pmids(raw: str) -> list[str]:
    """Pull digit-only PMIDs out of a free-form reference string, in order, de-duplicated.

    Handles bare digits, the bracketed/prefixed `[PMID: N]` / `PMID N` forms, and `;`-joined
    lists. Returns an empty list when the string carries no PMID token (e.g. a dbSNP URL)."""
    seen: dict[str, None] = {}
    for match in PMID_PATTERN.finditer(raw):
        seen.setdefault(match.group(1), None)
    return list(seen)


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
    panel: Optional[GenePanelSpec] = Field(
        default=None,
        description=(
            "Optional gene-panel declaration (ROADMAP item 7). Descriptive provenance for modules "
            "derived from a gene set + significance predicate; the compiler records it verbatim "
            "but does not materialize variants from it in this version."
        ),
    )
    authorship: list[Contribution] = Field(
        default_factory=list,
        description=(
            "Optional structured per-version authorship (RM14): one entry per contributor with "
            "who/role/kind (+ optional date). Recorded verbatim into the manifest; out of "
            "`artifact.digest`. A joint contribution is two entries (a human and an ai)."
        ),
    )

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
    start: Optional[int] = Field(
        default=None, ge=0, description="0-based genomic position (GRCh38)"
    )
    ref: Optional[str] = Field(default=None, description="Reference allele")
    alts: Optional[str] = Field(default=None, description="Alt allele(s), comma-separated")
    genotype: str = Field(description="Slash-separated sorted alleles, e.g. A/G")
    weight: Optional[float] = Field(default=None, description="Score (positive=protective)")
    state: str = Field(description="One of: risk, protective, neutral, significant, alt, ref")
    conclusion: str = Field(description="Human-readable interpretation for this genotype")
    negatives: Optional[str] = Field(
        default=None,
        description=(
            "Optional free-text adverse/antagonistic-pleiotropy counterpart to `conclusion` "
            "(e.g. a protective allele's known trade-off). Consumers ignore it when absent."
        ),
    )
    priority: Optional[str] = Field(default=None, description="Priority level override")
    gene: Optional[str] = Field(default=None, description="Gene symbol, e.g. MTHFR")
    phenotype: Optional[str] = Field(default=None, description="Associated trait or phenotype")
    category: Optional[str] = Field(default=None, description="Grouping category within the module")
    clinvar: Optional[bool] = Field(default=None, description="Is this variant in ClinVar?")
    pathogenic: Optional[bool] = Field(default=None, description="ClinVar pathogenic flag")
    benign: Optional[bool] = Field(default=None, description="ClinVar benign flag")
    curator: Optional[str] = Field(default=None, description="Curator override")
    method: Optional[str] = Field(default=None, description="Annotation method override")

    # ── 0.3 additive columns (all optional; see docs/ROADMAP.md "Planned for 0.3") ──
    direction: Optional[str] = Field(
        default=None,
        description="Effect direction: one of protective|risk|neutral|unknown. Orthogonal to `state`.",
    )
    stat_significance: Optional[str] = Field(
        default=None,
        description="Statistical significance: significant|suggestive|not_significant|unknown.",
    )
    effect_size: Optional[float] = Field(
        default=None, description="Published effect magnitude (unit given by `effect_measure`)."
    )
    effect_measure: Optional[str] = Field(
        default=None,
        description="Unit of `effect_size`, e.g. OR|HR|beta|RR (recommended; not a closed set).",
    )
    effect_allele: Optional[str] = Field(
        default=None,
        description="The allele that `direction`/`weight`/`effect_size` refer to (nucleotides).",
    )
    flags: Optional[list[str]] = Field(
        default=None,
        description=(
            "Open, multi-valued tag list (CSV: comma/semicolon/pipe-separated). Reserved tags the "
            "tooling acts on: conditional|phased|pleiotropic; other tags are allowed (surfaced as INFO)."
        ),
    )
    trait_efo_id: Optional[str] = Field(
        default=None,
        description="EFO/MONDO/OBA/HP trait ontology id(s), e.g. EFO_0001645 (matches just-prs).",
    )
    clin_sig: Optional[str] = Field(
        default=None,
        description="ClinVar/ACMG clinical significance (VEP CLIN_SIG vocabulary).",
    )

    # ── 0.4 general annotation axes (all optional; retired from the reserved namespace) ──
    # General per-variant refinements — any variant finding may carry them, so they live here rather
    # than in a domain table. A sparse SNP CSV simply omits them.
    requires_callable: Optional[bool] = Field(
        default=None,
        description=(
            "True when the *absence* of this variant is the informative call (recessive carrier, "
            "'pathogenic variant absent' reassurance) — a consumer lacking callability data must "
            "then withhold the reference/absence conclusion, never assert it (no-call ≠ hom-ref)."
        ),
    )
    acmg_sf: Optional[bool] = Field(
        default=None, description="True when the gene is on the ACMG secondary-findings list."
    )
    actionability: Optional[str] = Field(
        default=None,
        description=(
            "Annotation-level actionability of the finding (ACTIONABILITY_SEED: actionable|"
            "preventable|pharmacogenomic|incurable|reproductive|descriptive|modifiable). A property "
            "of the gene–condition–intervention triad a consumer's disclosure policy may read; the "
            "format never decides disclosure."
        ),
    )

    @property
    def variant_key(self) -> str:
        """Stable grouping key: rsid when available, else chrom:start:ref."""
        if self.rsid is not None:
            return self.rsid
        return f"{self.chrom}:{self.start}:{self.ref}"

    # ── 0.3 read-time aliases + upgrade (ROADMAP item 1/6 + "Upgrade derivation"). ────────────────
    # `state` and the ClinVar booleans stay REQUIRED/authoritative for 0.2 compat (CONSTITUTION
    # Principle 3/8 — a required field is never demoted to optional inside a major). These accessors
    # expose the orthogonal 0.3 axes even for a legacy row that set only `state`, by deriving when the
    # new column is absent; `upgraded()` materializes those derivations for a re-publish. All are
    # total and idempotent (CONSTITUTION Principle 7).
    @property
    def effective_direction(self) -> str:
        """`direction` if set, else derived from the legacy `state` (+ `weight` sign)."""
        return self.direction or direction_from_state(self.state, self.weight)

    @property
    def effective_stat_significance(self) -> str:
        """`stat_significance` if set, else derived from the legacy `state`."""
        return self.stat_significance or stat_significance_from_state(self.state)

    @property
    def effective_clin_sig(self) -> Optional[str]:
        """`clin_sig` if set, else derived from the legacy ClinVar booleans (lossy)."""
        return self.clin_sig or clin_sig_from_booleans(
            self.pathogenic, self.benign, self.clinvar
        )

    @property
    def effective_pathogenic(self) -> Optional[bool]:
        """The authoritative `pathogenic` boolean, or the one implied by `clin_sig` when unset."""
        if self.pathogenic is not None:
            return self.pathogenic
        return pathogenic_from_clin_sig(self.clin_sig)

    @property
    def effective_benign(self) -> Optional[bool]:
        """The authoritative `benign` boolean, or the one implied by `clin_sig` when unset."""
        if self.benign is not None:
            return self.benign
        return benign_from_clin_sig(self.clin_sig)

    def upgraded(self) -> "VariantRow":
        """A copy with the 0.3 axes back-populated from `state`/booleans and `state` trimmed to the
        legacy set {protective, risk, neutral}. `state` stays present (never dropped inside a major)
        but becomes a derived mirror of `direction`. Idempotent: ``r.upgraded().upgraded() ==
        r.upgraded()``."""
        direction = self.effective_direction
        return self.model_copy(
            update={
                "direction": direction,
                "stat_significance": self.effective_stat_significance,
                "clin_sig": self.effective_clin_sig,
                "pathogenic": self.effective_pathogenic,
                "benign": self.effective_benign,
                "state": trimmed_state(direction),
            }
        )

    @property
    def needs_upgrade(self) -> bool:
        """True when a re-publish would materialize a 0.3 column that is currently derived-but-empty
        (or would re-align the legacy `state`). Feeds the marketplace `revalidate`/`needs_upgrade`
        contract-drift flow (which flags drifted-but-fixable modules for a new PATCH)."""
        return self.upgraded() != self

    @field_validator("rsid")
    @classmethod
    def _validate_rsid(cls, v: Optional[str]) -> Optional[str]:
        return validate_rsid(v)

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
        # Phased (order-significant): pipe-separated, exactly two alleles, NOT sorted — phase encodes
        # which allele sits on which homolog. ROADMAP 0.3 item 5b.
        if "|" in v:
            parts = v.split("|")
            if len(parts) != 2:
                raise ValueError(
                    f"phased genotype must be two pipe-separated alleles (e.g. A|G), got: {v!r}"
                )
            for allele in parts:
                if not ALLELE_PATTERN.match(allele):
                    raise ValueError(
                        f"genotype alleles must be nucleotides, got: {allele!r} in {v!r}"
                    )
            return v
        parts = v.split("/")
        if len(parts) == 1:
            # Hemizygous single allele (non-PAR X/Y in males; homoplasmic MT). ROADMAP 0.3 item 5b.
            if not ALLELE_PATTERN.match(parts[0]):
                raise ValueError(f"genotype allele must be nucleotides, got: {v!r}")
            return v
        if len(parts) == 2:
            for allele in parts:
                if not ALLELE_PATTERN.match(allele):
                    raise ValueError(
                        f"genotype alleles must be nucleotides, got: {allele!r} in {v!r}"
                    )
            if parts != sorted(parts):
                raise ValueError(
                    f"unphased genotype alleles must be alphabetically sorted: "
                    f"expected {'/'.join(sorted(parts))!r}, got: {v!r}"
                )
            return v
        raise ValueError(
            f"genotype must be a single allele (hemizygous, e.g. A), two sorted slash-separated "
            f"alleles (A/G), or two pipe-separated phased alleles (A|G), got: {v!r}"
        )

    @field_validator("direction")
    @classmethod
    def _validate_direction(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_DIRECTIONS, "direction")

    @field_validator("stat_significance")
    @classmethod
    def _validate_stat_significance(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_SIGNIFICANCE, "stat_significance")

    @field_validator("clin_sig")
    @classmethod
    def _validate_clin_sig(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_CLIN_SIG, "clin_sig")

    @field_validator("actionability")
    @classmethod
    def _validate_actionability(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, ACTIONABILITY_SEED, "actionability")

    @field_validator("effect_allele")
    @classmethod
    def _validate_effect_allele(cls, v: Optional[str]) -> Optional[str]:
        return validate_allele(v, "effect_allele")

    @field_validator("weight")
    @classmethod
    def _validate_weight(cls, v: Optional[float]) -> Optional[float]:
        return validate_finite(v, "weight")

    @field_validator("effect_size")
    @classmethod
    def _validate_effect_size(cls, v: Optional[float]) -> Optional[float]:
        return validate_finite(v, "effect_size")

    @field_validator("flags", mode="before")
    @classmethod
    def _split_flags(cls, v: object) -> object:
        # A CSV cell arrives as a string; split it into a list. Programmatic construction may pass a
        # list already. The vocabulary is OPEN — unknown tags are accepted (the compiler surfaces
        # them as INFO), so nothing is rejected here beyond emptiness.
        if isinstance(v, str):
            tags = [t.strip() for t in _MULTI_SEP.split(v) if t.strip()]
            return tags or None
        return v

    @field_validator("flags")
    @classmethod
    def _validate_flags(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        if v is None:
            return v
        for tag in v:
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(f"flags entries must be non-empty strings, got: {v!r}")
        return v

    @field_validator("trait_efo_id")
    @classmethod
    def _validate_trait_efo_id(cls, v: Optional[str]) -> Optional[str]:
        return validate_trait_ids(v)

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
    start: Optional[int] = Field(
        default=None, ge=0, description="0-based position (position-only variants)"
    )
    ref: Optional[str] = Field(default=None, description="Reference allele (position-only variants)")
    pmid: str = Field(description="PubMed ID or reference — free-form, must be non-empty")
    population: Optional[str] = Field(default=None, description="Study population")
    p_value: Optional[str] = Field(default=None, description="Raw p-value string (free-form)")
    conclusion: Optional[str] = Field(default=None, description="Study-specific conclusion")
    study_design: Optional[str] = Field(default=None, description="e.g. meta-analysis, GWAS")

    # ── 0.3 additive columns (per-study evidence; see docs/ROADMAP.md "Planned for 0.3") ──
    stat_significance: Optional[str] = Field(
        default=None,
        description="Per-study statistical significance: significant|suggestive|not_significant|unknown.",
    )
    effect_size: Optional[float] = Field(
        default=None, description="Per-study effect magnitude (unit given by `effect_measure`)."
    )
    effect_measure: Optional[str] = Field(
        default=None, description="Unit of `effect_size`, e.g. OR|HR|beta|RR (recommended, open)."
    )
    trait_efo_id: Optional[str] = Field(
        default=None, description="EFO/MONDO/OBA/HP trait ontology id(s) for this study."
    )

    # ── 0.5 additive provenance columns (RM11/RM12; docs/USE_CASES.md §4a) ──
    # All optional → P3/P8 clean. They anchor a network-first validator (RM13) without the format
    # ever fetching: the module ships the pointer, the consumer supplies the source and does the check.
    doi: Optional[str] = Field(
        default=None,
        description=(
            "Digital Object Identifier — wider than `pmid` (covers preprints/books/datasets with no "
            "PubMed id). Free-form, kept verbatim; a validator may cross-fill doi↔pmid."
        ),
    )
    provenance_quote: Optional[str] = Field(
        default=None,
        description=(
            "Optional keyword phrase / literal passage locating this study's claim in the cited "
            "article's fulltext. Human-legible; a validator confirms fulltext-contains, yes/no."
        ),
    )
    provenance_regex: Optional[str] = Field(
        default=None,
        description=(
            "Optional regex locating the claim in fulltext — a declarative pattern grammar "
            "(Principle 1: data, not code), matched consumer-side by a linear-time/ReDoS-safe engine."
        ),
    )

    @property
    def variant_key(self) -> str:
        """Stable key matching VariantRow.variant_key."""
        if self.rsid is not None:
            return self.rsid
        return f"{self.chrom}:{self.start}:{self.ref}"

    @field_validator("stat_significance")
    @classmethod
    def _validate_stat_significance(cls, v: Optional[str]) -> Optional[str]:
        return check_vocab(v, VALID_SIGNIFICANCE, "stat_significance")

    @field_validator("effect_size")
    @classmethod
    def _validate_effect_size(cls, v: Optional[float]) -> Optional[float]:
        return validate_finite(v, "effect_size")

    @field_validator("trait_efo_id")
    @classmethod
    def _validate_trait_efo_id(cls, v: Optional[str]) -> Optional[str]:
        return validate_trait_ids(v)

    @field_validator("rsid")
    @classmethod
    def _validate_rsid(cls, v: Optional[str]) -> Optional[str]:
        return validate_rsid(v)

    @field_validator("pmid")
    @classmethod
    def _validate_pmid(cls, v: str) -> str:
        v = str(v).strip()
        if not v:
            raise ValueError("pmid must not be empty")
        if not extract_pmids(v):
            raise ValueError(
                f"pmid must contain at least one PubMed ID (bare digits, or a bracketed/prefixed "
                f"form like '[PMID: 9545397]'), got: {v!r}"
            )
        return v  # kept verbatim; use extract_pmids(pmid) to recover digit-only ids

    @field_validator("doi")
    @classmethod
    def _validate_doi(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not DOI_PATTERN.search(v):
            raise ValueError(
                f"doi must contain a DOI token (10.<registrant>/<suffix>, bare or as a doi.org "
                f"URL), got: {v!r}"
            )
        return v  # kept verbatim

    @field_validator("provenance_regex")
    @classmethod
    def _validate_provenance_regex(cls, v: Optional[str]) -> Optional[str]:
        # Author-time sanity: the pattern must compile. ReDoS-safety is the consumer's concern —
        # it evaluates the pattern with a linear-time engine (Principle 1), never Python `re`.
        if v is None:
            return v
        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"provenance_regex is not a valid regular expression: {exc}") from exc
        return v

    @model_validator(mode="after")
    def _validate_study_identification(self) -> "StudyRow":
        if self.rsid is None and self.chrom is None:
            raise ValueError(
                "At least one identifier is required: provide rsid or position (chrom + start)"
            )
        return self
