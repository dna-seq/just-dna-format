"""
The `manifest.json` contract — the single source of truth for a compiled annotation module.

Mirrors SPEC §4. Fields known at compile time (display, stats, compilation, inputs, artifact)
are filled by the compiler; marketplace-level fields (namespace, version, owner, license,
published_at, canonical_id) are `Optional` and filled by the marketplace on publish.

This module is intentionally dependency-light (Pydantic + stdlib only) so both
`just-dna-pipelines` (which emits the manifest) and `just-dna-marketplace` (which consumes and
extends it) can share one definition without pulling heavy transitive dependencies.
"""

import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from just_dna_format.identity import (
    is_valid_version,
    validate_name,
    validate_namespace,
)
from just_dna_format.vocab import (
    RECOMMENDED_AUTHOR_KINDS,
    VALID_AUTHOR_ROLES,
    check_vocab,
)

MANIFEST_VERSION: str = "1.0"
SCHEMA_VERSION: str = "1.0"

# The only `compiled_by` value a downloader trusts (SPEC §5).
MARKETPLACE_COMPILED_BY: str = "marketplace-server"

# Mirrors just-dna-pipelines ModuleInfo.color validation (module_compiler/models.py).
COLOR_PATTERN: re.Pattern[str] = re.compile(r"^#[0-9a-fA-F]{6}$")

# Icon families a module may draw its no-logo fallback glyph from.
VALID_ICON_SETS: frozenset[str] = frozenset({"fomantic", "awesome"})
# Accepted raster logo extensions (lowercase, no dot).
LOGO_EXTENSIONS: frozenset[str] = frozenset({"png", "jpg", "jpeg"})

# A curated authoring palette (RM9): recommended `Display.color`/`icon` values by semantic use, so an
# authoring UI / LLM picks from one shared set instead of inventing its own (just-dna-agents' MCP
# `list_colors`/`list_icons` are the drift this replaces). Recommendation only — NOT enforced: `color`
# is validated by `COLOR_PATTERN` and `icon` is free-form within `icon_set`. Icons name Fomantic UI
# glyphs (the default `icon_set`); colours are the Fomantic semantic hexes.
RECOMMENDED_COLORS: dict[str, str] = {
    "risk": "#db2828",
    "protective": "#21ba45",
    "neutral": "#767676",
    "pharmacogenomic": "#6435c9",
    "cardiometabolic": "#00b5ad",
    "cancer": "#f2711c",
    "neuro": "#a333c8",
    "info": "#2185d0",
    "reproductive": "#e03997",
}
RECOMMENDED_ICONS: dict[str, str] = {
    "default": "database",
    "dna": "dna",
    "cardiometabolic": "heartbeat",
    "cancer": "ribbon",
    "pharmacogenomic": "pills",
    "neuro": "brain",
    "lab": "flask",
    "protective": "shield",
    "reproductive": "baby",
}


class Identity(BaseModel):
    """Module identity. `namespace`/`version`/`canonical_id` are filled by the marketplace.

    Identity rules are validated here using the shared `just_dna_format.identity` helpers, so
    the contract enforces exactly what just-dna-pipelines enforces on `module_spec.yaml`.
    """

    namespace: Optional[str] = Field(default=None, description="Owning account/org slug")
    name: str = Field(description="Machine name, matches ^[a-z][a-z0-9_]*$")
    version: Optional[str] = Field(default=None, description="SemVer MAJOR.MINOR.PATCH")
    canonical_id: Optional[str] = Field(
        default=None, description="namespace/name@version"
    )

    @field_validator("name")
    @classmethod
    def _check_name(cls, v: str) -> str:
        return validate_name(v)

    @field_validator("namespace")
    @classmethod
    def _check_namespace(cls, v: Optional[str]) -> Optional[str]:
        return None if v is None else validate_namespace(v)

    @field_validator("version")
    @classmethod
    def _check_version(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not is_valid_version(v):
            raise ValueError(f"version must be MAJOR.MINOR.PATCH, got: {v!r}")
        return v


class Display(BaseModel):
    """Shared display metadata for a module. The authoring DSL's `spec.ModuleInfo` extends this
    (adding `name`), so the fields and their validation are defined here once."""

    title: str
    description: str
    report_title: str
    icon: str = Field(
        default="database", description="Icon name within `icon_set` — the no-logo fallback glyph"
    )
    icon_set: str = Field(
        default="fomantic", description="Icon family for `icon`: 'fomantic' or 'awesome' (FontAwesome)"
    )
    color: str = Field(default="#6435c9", description="Hex color for UI theming")

    @field_validator("color")
    @classmethod
    def _check_color(cls, v: str) -> str:
        if not COLOR_PATTERN.match(v):
            raise ValueError(f"color must be a 6-digit hex code like #21ba45, got: {v!r}")
        return v

    @field_validator("icon_set")
    @classmethod
    def _check_icon_set(cls, v: str) -> str:
        if v not in VALID_ICON_SETS:
            raise ValueError(f"icon_set must be one of {sorted(VALID_ICON_SETS)}, got: {v!r}")
        return v


class Stats(BaseModel):
    """Card/detail stats derived from the spec at compile time.

    `clinvar_count`/`pathogenic_count`/`benign_count` summarize the per-row ClinVar quality flags
    that `weights.parquet` already carries, so consumers can facet on them without reading the
    artifact (SPEC ROADMAP item 5). They are additive and default to 0 for older manifests.
    """

    variant_count: int = 0
    weights_rows: int = 0
    study_count: int = 0
    gene_count: int = 0
    genes: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    clinvar_count: int = Field(default=0, description="Rows flagged in ClinVar")
    pathogenic_count: int = Field(default=0, description="Rows flagged ClinVar-pathogenic")
    benign_count: int = Field(default=0, description="Rows flagged ClinVar-benign")


class Compilation(BaseModel):
    """Provenance of the compile that produced this artifact (SPEC §5 trust fields)."""

    compile_success: bool = False
    compiled_by: Optional[str] = Field(
        default=None, description="e.g. 'marketplace-server'; foreign values are untrusted"
    )
    compiler_version: Optional[str] = None
    ensembl_reference: Optional[str] = Field(
        default=None, description="Pinned Ensembl reference, e.g. org/repo@<rev>"
    )
    compiled_at: Optional[str] = Field(default=None, description="ISO-8601 UTC timestamp")
    warnings: list[str] = Field(default_factory=list)


class FileEntry(BaseModel):
    """One hashed file — used for both `inputs[]` and `artifact.files[]` (SPEC §5)."""

    name: str
    sha256: str = Field(description="Lowercase hex digest, prefixed 'sha256:'")
    size: int = Field(description="Byte size of the file")


class Artifact(BaseModel):
    """The compiled output set plus its Merkle-root digest (the content identity)."""

    digest: str = Field(description="sha256: over the canonical file listing (SPEC §5)")
    files: list[FileEntry] = Field(default_factory=list)


class GenePanelSpec(BaseModel):
    """Declares a module derived from a *gene set + significance predicate* over a reference,
    rather than an enumerated variant table (SPEC ROADMAP item 7).

    This is the authored *interface* only: the compiler records it verbatim but does not
    materialize it (an app-level adapter enumerates the matching variants into `variants.csv`
    today). Native compile-time materialization is a follow-up gated on a working ClinVar
    reference mixin. Optional and backwards-compatible — absent on ordinary variant modules.
    """

    source: str = Field(description="Reference the panel resolves against, e.g. 'clinvar'")
    reference: Optional[str] = Field(
        default=None, description="Reference release/version id, e.g. a ClinVar release date"
    )
    reference_sha256: Optional[str] = Field(
        default=None, description="Digest pinning the exact reference resource (sha256:...)"
    )
    genes: list[str] = Field(
        default_factory=list, description="Panel gene symbols; empty = genome-wide (no gene filter)"
    )
    significance: list[str] = Field(
        default_factory=list,
        description="Significance predicate, e.g. ['pathogenic', 'likely_pathogenic']",
    )


class ProvenanceItem(BaseModel):
    """One per-variant provenance record (SPEC ROADMAP item 1). Lives in the full `provenance.json`
    document, not in the manifest — the manifest carries only the `Provenance` summary pointer."""

    variant_key: str = Field(description="rsid or chrom:start:ref, matching VariantRow.variant_key")
    rationale: Optional[str] = Field(default=None, description="Why this annotation was made")
    reviewer_verdict: Optional[str] = Field(default=None, description="Reviewer's verdict, if any")
    confidence: Optional[float] = Field(default=None, description="Author/model confidence 0..1")
    human_reviewed: bool = Field(default=False, description="A human reviewed this item")


class ProvenanceDoc(BaseModel):
    """The full `provenance.json` authored beside the spec: a header plus per-variant items. The
    compiler reads and hashes it, then records the lean `Provenance` summary in the manifest so
    catalog cards can flag 'AI-authored · rationale available' without inlining the full text."""

    generator: Optional[str] = Field(default=None, description="Tool/pipeline that produced items")
    model: Optional[str] = Field(default=None, description="Model id, if AI-authored")
    agent_version: Optional[str] = Field(default=None, description="Agent/framework version")
    items: list[ProvenanceItem] = Field(default_factory=list)


class Provenance(BaseModel):
    """Lean summary pointer to a version's `provenance.json` (SPEC ROADMAP item 1). The full items
    live in the hashed file (kept out of `artifact.digest`, like `logs`); this rides in the manifest."""

    generator: Optional[str] = None
    model: Optional[str] = None
    agent_version: Optional[str] = None
    item_count: int = 0
    file: Optional[str] = Field(
        default=None, description="Path to the provenance document relative to the module dir"
    )
    sha256: Optional[str] = Field(default=None, description="sha256: of the provenance document")


class Contribution(BaseModel):
    """One authorship contribution to *this version* of a module (RM14; docs/USE_CASES.md §5a).

    Three orthogonal axes (Principle 5), unbundling the flat `authors`/free-form `curator`:
    `who` (identity), `role` (what they did — closed vocab), and `kind` (a multi-valued tag set
    describing the contributor: a human ladder of assurance `human` → `human_expert` →
    `human_certified`, or `ai` with a scale tag `agent`/`team`/`swarm` — open, so new tags may be
    coined). A joint contribution is two entries (a human and an ai), each with its own `kind`, so
    the mix is always spelled out and there is no lossy `hybrid` tag.

    Module metadata: carried in the manifest, **out of `artifact.digest`** (like `provenance`/`logs`),
    so two versions with identical annotation content but different authorship share a content
    identity. A consumer (the network validator, a review queue, a human auditor) routes its scrutiny
    by `kind` — the format carries the kind, the consumer picks the profile (the data-agnostic north
    star). `extra="forbid"` keeps the record's namespace closed."""

    model_config = ConfigDict(extra="forbid")

    who: str = Field(description="Contributor identity: a name, handle, or model id")
    role: str = Field(description="What this contributor did (created|edited|audited|reviewed)")
    kind: list[str] = Field(
        default_factory=list,
        description=(
            "Multi-valued tag set describing the contributor — human ladder {human, human_expert, "
            "human_certified} or {ai} + scale {agent, team, swarm}. Open (recommended seed); route "
            "scrutiny by it."
        ),
    )
    at: Optional[str] = Field(default=None, description="ISO-8601 date/timestamp of the contribution")

    @field_validator("who")
    @classmethod
    def _check_who(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("who must not be empty")
        return v

    @field_validator("role")
    @classmethod
    def _check_role(cls, v: str) -> str:
        # A closed vocabulary (Principle 6); reuse the shared checker's message format.
        check_vocab(v, VALID_AUTHOR_ROLES, "role")  # raises if outside the vocab; role is required
        return v

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, v: list[str]) -> list[str]:
        # OPEN tag set: normalise to non-empty lowercase tokens, de-duplicated in order. Unknown tags
        # (outside RECOMMENDED_AUTHOR_KINDS) are kept, not rejected — new AI topologies may be coined.
        cleaned: list[str] = []
        for tag in v:
            tok = tag.strip().lower()
            if not tok:
                raise ValueError("kind tags must be non-empty")
            if tok not in cleaned:
                cleaned.append(tok)
        if not cleaned:
            raise ValueError(
                f"kind must list at least one tag (recommended: {sorted(RECOMMENDED_AUTHOR_KINDS)})"
            )
        return cleaned


class Signature(BaseModel):
    """Optional detached signature over `artifact.digest` (SPEC §5 'future'). Defends against a
    compromised storage backend: a client that pins the marketplace's public key can prove the
    digest was signed by the trusted party."""

    algorithm: str = Field(default="ed25519", description="Signature algorithm")
    public_key: str = Field(description="Base64 (raw) Ed25519 public key")
    signature: str = Field(description="Base64 signature over the artifact.digest string bytes")
    signed_at: Optional[str] = Field(default=None, description="ISO-8601 UTC timestamp")


class ModuleManifest(BaseModel):
    """Full module manifest (SPEC §4). Written next to the parquets as `manifest.json`."""

    manifest_version: str = MANIFEST_VERSION
    schema_version: str = SCHEMA_VERSION

    identity: Identity
    display: Display

    genome_build: str = Field(
        default="GRCh38",
        description=(
            "Reference genome build. The reference compiler is GRCh38-bound — the digest is "
            "GRCh38-relative; other builds are recorded but not honored (RM15)."
        ),
    )
    curator: Optional[str] = None
    method: Optional[str] = None
    license: Optional[str] = None

    owner: Optional[str] = None
    authors: list[str] = Field(default_factory=list)
    authorship: list[Contribution] = Field(
        default_factory=list,
        description=(
            "Structured per-version authorship (RM14): who created/edited/audited this version, and "
            "whether each is AI or a human expert — so a consumer routes scrutiny by author-kind. "
            "Optional, out of `artifact.digest`. Supersedes the flat `authors`/`curator` (kept for "
            "compat; folding them in is a 1.0-cleanup item)."
        ),
    )
    created_at: Optional[str] = None
    published_at: Optional[str] = None

    stats: Stats = Field(default_factory=Stats)
    compilation: Compilation = Field(default_factory=Compilation)
    inputs: list[FileEntry] = Field(default_factory=list)
    artifact: Artifact
    logs: list[FileEntry] = Field(
        default_factory=list,
        description=(
            "Optional per-version run/provenance log files, hashed like inputs. Each `name` is a "
            "path relative to the module dir, so both a top-level aggregate log (e.g. `run.log`) "
            "and per-role files under a `logs/` folder (e.g. `logs/researcher.log`, "
            "`logs/reviewer.log`) are supported. Absent logs do NOT invalidate a module. Kept out "
            "of `artifact.digest` so identical compiled data stays dedup-equal regardless of logs; "
            "full cross-version provenance is the union of every version's logs."
        ),
    )
    provenance: Optional[Provenance] = Field(
        default=None,
        description=(
            "Optional summary of a version's structured per-variant provenance (SPEC ROADMAP item "
            "1). The full items live in a hashed `provenance.json` (kept out of `artifact.digest`, "
            "like `logs`); this field carries only the generator/model/count/hash pointer."
        ),
    )
    panel: Optional[GenePanelSpec] = Field(
        default=None,
        description=(
            "Set when the module was authored as a gene panel (SPEC ROADMAP item 7). Descriptive "
            "only in this version — the variant set is still enumerated in the artifact."
        ),
    )
    logo: Optional[FileEntry] = Field(
        default=None,
        description=(
            "Optional module logo image (png/jpg/jpeg), hashed like `inputs`. Kept OUT of "
            "`artifact.digest` so a logo swap is a PATCH (metadata only), not a new content "
            "identity. Consumers fall back to `display.icon`/`icon_set` when absent."
        ),
    )
    signature: Optional[Signature] = Field(
        default=None,
        description="Optional detached Ed25519 signature over `artifact.digest` (SPEC §5).",
    )


def read_manifest(path: Path) -> ModuleManifest:
    """Load and validate a `manifest.json` from disk."""
    return ModuleManifest.model_validate_json(Path(path).read_text(encoding="utf-8"))


def write_manifest(manifest: ModuleManifest, path: Path) -> Path:
    """Write a manifest to disk as indented JSON. Returns the path written."""
    path = Path(path)
    path.write_text(
        manifest.model_dump_json(indent=2, exclude_none=False) + "\n", encoding="utf-8"
    )
    return path
