"""
Module spec compiler: validates a spec directory and compiles it to the three-parquet artifact
(weights, annotations, studies) plus a `manifest.json`.

Public API:
    validate_spec(spec_dir) -> ValidationResult
    compile_module(spec_dir, output_dir, ...) -> CompilationResult   (emits manifest.json)
    reverse_module(parquet_dir, output_dir, ...) -> Path

The DSL/manifest schema comes from `just-dna-format`; this package is the transform between them.
"""

import csv
import re
import shutil
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Optional

import polars as pl
import yaml
from just_dna_format.integrity import build_artifact, file_entries, file_entry, sha256_file
from just_dna_format.manifest import (
    LOGO_EXTENSIONS,
    Compilation,
    Display,
    FileEntry,
    Identity,
    ModuleManifest,
    Provenance,
    ProvenanceDoc,
    Stats,
    write_manifest,
)
from just_dna_format.spec import RESERVED_FLAGS, ModuleSpecConfig, StudyRow, VariantRow
from pydantic import ValidationError

from just_dna_compiler.models import CompilationResult, ValidationResult

# Genotype allele separators: `/` (unphased), `|` (phased). See ROADMAP 0.3 item 5b. Splitting on
# both yields the allele list; phase (the `|` vs `/` distinction) is NOT preserved in the artifact —
# that is an intentionally-deferred computed item (see docs/COMPILER.md).
_GENOTYPE_SEP: re.Pattern[str] = re.compile(r"[/|]")


def _split_genotype(genotype: str) -> list[str]:
    """Split a genotype string into its alleles, accepting single-allele (hemizygous),
    slash-separated (unphased), and pipe-separated (phased) forms."""
    return [allele for allele in _GENOTYPE_SEP.split(genotype) if allele]

_INPUT_FILES: tuple[str, ...] = ("module_spec.yaml", "variants.csv", "studies.csv")
_OUTPUT_FILES: tuple[str, ...] = ("weights.parquet", "annotations.parquet", "studies.parquet")
# Optional structured-provenance document authored beside the spec (ROADMAP item 1). Hashed and
# shipped like logs, kept OUT of `artifact.digest` (it is not in `_OUTPUT_FILES`).
_PROVENANCE_FILE: str = "provenance.json"


def _compiler_version() -> str:
    try:
        return f"just-dna-compiler {version('just-dna-compiler')}"
    except PackageNotFoundError:
        return "just-dna-compiler unknown"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _collect_logs(
    spec_dir: Path, output_dir: Path, explicit: Optional[list[Path]]
) -> list[FileEntry]:
    """Gather optional run/provenance logs into the module dir and hash them.

    Auto-discovers a top-level aggregate log (`*.log` in `spec_dir`) plus per-role files under a
    `spec_dir/logs/` folder, preserving each file's path relative to the module. An explicit
    `log_files` list overrides discovery. Files are copied into `output_dir` (so they ship with the
    module) and returned as hashed `FileEntry` rows. No logs → empty list (a valid module).
    """
    pairs: list[tuple[str, Path]] = []  # (relative name in module dir, source file)
    if explicit is not None:
        for path in map(Path, explicit):
            try:
                rel = path.relative_to(spec_dir).as_posix()
            except ValueError:
                rel = path.name
            pairs.append((rel, path))
    else:
        for path in sorted(spec_dir.glob("*.log")):
            pairs.append((path.name, path))
        logs_dir = spec_dir / "logs"
        if logs_dir.is_dir():
            for path in sorted(logs_dir.rglob("*.log")):
                pairs.append((path.relative_to(spec_dir).as_posix(), path))

    seen: set[str] = set()
    names: list[str] = []
    for rel, src in pairs:
        if rel in seen or not src.is_file():
            continue
        seen.add(rel)
        dest = output_dir / rel
        if dest.resolve() != src.resolve():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
        names.append(rel)
    return file_entries(output_dir, names)


def _collect_provenance(
    spec_dir: Path, output_dir: Path, explicit: Optional[Path]
) -> Optional[Provenance]:
    """Discover an optional `provenance.json`, validate it, ship it, and summarize it.

    Auto-discovers `spec_dir/provenance.json` (or uses an explicit path). The full per-variant
    items stay in the file (copied into the module dir, hashed like logs, and kept out of
    `artifact.digest`); the returned `Provenance` is the lean summary that rides in the manifest.
    Absent provenance → `None` (a valid module).
    """
    src = Path(explicit) if explicit is not None else spec_dir / _PROVENANCE_FILE
    if not src.is_file():
        return None
    doc = ProvenanceDoc.model_validate_json(src.read_text(encoding="utf-8"))
    dest = output_dir / _PROVENANCE_FILE
    if dest.resolve() != src.resolve():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    return Provenance(
        generator=doc.generator,
        model=doc.model,
        agent_version=doc.agent_version,
        item_count=len(doc.items),
        file=_PROVENANCE_FILE,
        sha256=sha256_file(dest),
    )


def _collect_logo(
    spec_dir: Path, output_dir: Path, explicit: Optional[Path]
) -> Optional[FileEntry]:
    """Discover an optional module logo (`logo.png`/`.jpg`/`.jpeg`), ship it, and hash it.

    Uses an explicit path if given, else the first `logo.<ext>` (in `LOGO_EXTENSIONS` order) found
    beside the spec. The logo is copied into the module dir and returned as a hashed `FileEntry`
    kept OUT of `artifact.digest` (a logo swap is a PATCH, not a new content identity). Absent
    logo → `None`. Raises `ValueError` on an unsupported extension.
    """
    if explicit is not None:
        src: Optional[Path] = Path(explicit)
    else:
        src = next(
            (spec_dir / f"logo.{ext}" for ext in sorted(LOGO_EXTENSIONS)
             if (spec_dir / f"logo.{ext}").is_file()),
            None,
        )
    if src is None or not src.is_file():
        return None
    ext = src.suffix.lower().lstrip(".")
    if ext not in LOGO_EXTENSIONS:
        raise ValueError(f"logo must be one of {sorted(LOGO_EXTENSIONS)}, got: {src.name!r}")
    dest = output_dir / src.name
    if dest.resolve() != src.resolve():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
    return file_entry(output_dir, src.name)


# ── File loading helpers ───────────────────────────────────────────────────────


def _load_yaml(path: Path) -> tuple[Optional[ModuleSpecConfig], list[str]]:
    """Load and validate module_spec.yaml. Returns (config, errors)."""
    if not path.exists():
        return None, [f"module_spec.yaml not found at {path}"]
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return None, ["module_spec.yaml is empty"]
    try:
        return ModuleSpecConfig.model_validate(raw), []
    except ValidationError as exc:
        errors = []
        for err in exc.errors():
            loc = " → ".join(str(x) for x in err["loc"])
            errors.append(f"module_spec.yaml [{loc}]: {err['msg']}")
        return None, errors


def _load_csv_rows(
    path: Path, row_model: type, file_label: str
) -> tuple[list[Any], list[str], list[str]]:
    """Load a CSV and validate each row against a Pydantic model. Returns (rows, errors, warnings)."""
    errors: list[str] = []
    rows: list[Any] = []
    if not path.exists():
        return [], [f"{file_label} not found at {path}"], []

    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return [], [f"{file_label} has no header row"], []
        for line_num, raw_row in enumerate(reader, start=2):
            cleaned = {
                k.strip(): (v.strip() if isinstance(v, str) and v.strip() != "" else None)
                for k, v in raw_row.items()
                if k is not None
            }
            try:
                rows.append(row_model.model_validate(cleaned))
            except ValidationError as exc:
                for err in exc.errors():
                    loc = " → ".join(str(x) for x in err["loc"])
                    errors.append(f"{file_label} line {line_num} [{loc}]: {err['msg']}")
    return rows, errors, []


# ── Cross-row validation ───────────────────────────────────────────────────────


def _cross_validate_variants(variants: list[VariantRow]) -> tuple[list[str], list[str]]:
    """Validate consistency across variant rows. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []

    key_positions: dict[str, tuple[Optional[str], Optional[int]]] = {}
    for row in variants:
        key = row.variant_key
        pos = (row.chrom, row.start)
        if key in key_positions:
            if key_positions[key] != pos:
                errors.append(f"Inconsistent positions for {key}: {key_positions[key]} vs {pos}")
        else:
            key_positions[key] = pos

    seen_keys: set[tuple[str, str]] = set()
    for row in variants:
        key = (row.variant_key, row.genotype)
        if key in seen_keys:
            errors.append(f"Duplicate (variant, genotype): ({row.variant_key}, {row.genotype})")
        seen_keys.add(key)

    for row in variants:
        # `state`/`weight` sign consistency (legacy), plus the same check on the new `direction`.
        if row.weight is not None:
            if row.state == "risk" and row.weight > 0:
                warnings.append(
                    f"{row.variant_key} genotype {row.genotype}: state='risk' but weight={row.weight} > 0"
                )
            if row.state == "protective" and row.weight < 0:
                warnings.append(
                    f"{row.variant_key} genotype {row.genotype}: state='protective' but weight={row.weight} < 0"
                )
            if row.direction == "risk" and row.weight > 0:
                warnings.append(
                    f"{row.variant_key} genotype {row.genotype}: direction='risk' but weight={row.weight} > 0"
                )
            if row.direction == "protective" and row.weight < 0:
                warnings.append(
                    f"{row.variant_key} genotype {row.genotype}: direction='protective' but weight={row.weight} < 0"
                )
        # Non-diploid guardrail (ROADMAP 0.3 item 5b): MT and Y are never diploid, so a two-allele
        # genotype is almost certainly a "fake diploid" error — a homoplasmic MT call or a hemizygous
        # Y call is a single allele (e.g. 'G'). X is deliberately excluded: it is diploid in XX
        # samples, so a two-allele X row is legitimate (the item-5b dogfood enumerates both a
        # single-allele hemizygous row and the diploid rows at an X-linked locus); warning on X would
        # be pure noise. PAR vs non-PAR needs coordinates the format does not resolve — so Y (never
        # diploid regardless of sex) is the safe, false-positive-free half of "non-PAR X/Y".
        if row.chrom in {"MT", "Y"} and ("/" in row.genotype or "|" in row.genotype):
            warnings.append(
                f"{row.variant_key} genotype {row.genotype}: chrom={row.chrom} is not diploid — use "
                f"a single-allele genotype (e.g. 'G') for a homoplasmic/hemizygous call"
            )
    return errors, warnings


def _cross_validate_studies(
    studies: list[StudyRow], variant_keys: set[str]
) -> tuple[list[str], list[str]]:
    """Validate study rows against variant keys. Returns (errors, warnings)."""
    warnings: list[str] = []
    orphan_keys = {row.variant_key for row in studies} - variant_keys
    if orphan_keys:
        warnings.append(f"Studies reference variants not in variants.csv: {sorted(orphan_keys)}")
    seen: set[tuple[str, str]] = set()
    for row in studies:
        key = (row.variant_key, row.pmid)
        if key in seen:
            warnings.append(f"Duplicate (variant, pmid): ({row.variant_key}, {row.pmid})")
        seen.add(key)
    return [], warnings


# ── Public API ─────────────────────────────────────────────────────────────────


def validate_spec(spec_dir: Path) -> ValidationResult:
    """Validate a module spec directory without producing output.

    Stats include `genes`/`categories` as lists (filtering None) plus `variant_count`,
    `gene_count`, `study_count`, and the ClinVar quality counts
    (`clinvar_count`/`pathogenic_count`/`benign_count`) — the fields the manifest needs. See
    `ValidationResult.stats` for the full key contract.
    """
    spec_dir = Path(spec_dir)
    all_errors: list[str] = []
    all_warnings: list[str] = []
    all_info: list[str] = []

    if not spec_dir.is_dir():
        return ValidationResult(valid=False, errors=[f"Spec directory does not exist: {spec_dir}"])

    config, yaml_errors = _load_yaml(spec_dir / "module_spec.yaml")
    all_errors.extend(yaml_errors)

    variants, var_errors, var_warnings = _load_csv_rows(
        spec_dir / "variants.csv", VariantRow, "variants.csv"
    )
    all_errors.extend(var_errors)
    all_warnings.extend(var_warnings)

    studies_path = spec_dir / "studies.csv"
    studies: list[StudyRow] = []
    if studies_path.exists():
        studies, study_errors, study_warnings = _load_csv_rows(
            studies_path, StudyRow, "studies.csv"
        )
        all_errors.extend(study_errors)
        all_warnings.extend(study_warnings)
        if not studies and not study_errors:
            all_errors.append(
                "studies.csv is present but has no study rows. Grounding evidence is mandatory."
            )
    else:
        all_errors.append(
            "studies.csv is missing. Grounding evidence is mandatory; add study rows with PMIDs."
        )

    if variants:
        cross_errors, cross_warnings = _cross_validate_variants(variants)
        all_errors.extend(cross_errors)
        all_warnings.extend(cross_warnings)
        variant_keys = {v.variant_key for v in variants}
        if studies:
            _, study_warnings = _cross_validate_studies(studies, variant_keys)
            all_warnings.extend(study_warnings)
        # `flags` is an open vocabulary — surface non-reserved tags as INFO (not a warning; nothing
        # is wrong). ROADMAP 0.3 item 4.
        unknown_flags = sorted(
            {tag for v in variants if v.flags for tag in v.flags if tag not in RESERVED_FLAGS}
        )
        if unknown_flags:
            all_info.append(
                f"Non-reserved flags in use (allowed; reserved tags are "
                f"{sorted(RESERVED_FLAGS)}): {unknown_flags}"
            )

    stats: dict[str, Any] = {}
    if variants:
        variant_keys_set = {v.variant_key for v in variants}
        genes = sorted({v.gene for v in variants if v.gene})
        categories = sorted({v.category for v in variants if v.category})
        stats = {
            "variant_count": len(variant_keys_set),
            "unique_rsids": len({v.rsid for v in variants if v.rsid is not None}),
            "gene_count": len(genes),
            "genes": genes,
            "categories": categories,
            "study_count": len(studies),
            # ClinVar/quality flag counts over variant rows (ROADMAP item 5).
            "clinvar_count": sum(1 for v in variants if v.clinvar),
            "pathogenic_count": sum(1 for v in variants if v.pathogenic),
            "benign_count": sum(1 for v in variants if v.benign),
        }
        if config:
            stats["module_name"] = config.module.name

    return ValidationResult(
        valid=len(all_errors) == 0,
        errors=all_errors,
        warnings=all_warnings,
        info=all_info,
        stats=stats,
    )


def compile_module(
    spec_dir: Path,
    output_dir: Path,
    compression: str = "zstd",
    resolve_with_ensembl: bool = True,
    ensembl_cache: Optional[Path] = None,
    compiled_by: Optional[str] = None,
    ensembl_reference: Optional[str] = None,
    log_files: Optional[list[Path]] = None,
    provenance_file: Optional[Path] = None,
    logo_file: Optional[Path] = None,
) -> CompilationResult:
    """Compile a module spec directory into parquet files plus a `manifest.json`.

    Args:
        spec_dir: Path to the module spec directory.
        output_dir: Directory for output parquet files + manifest.json.
        compression: Parquet compression codec.
        resolve_with_ensembl: Resolve missing rsid/position via an injected Ensembl DuckDB.
        ensembl_cache: Path to a prebuilt Ensembl DuckDB or a parquet cache dir (required to
            resolve; the standalone compiler does not download it — the caller injects it).
        compiled_by: Provenance tag for the manifest (the marketplace passes "marketplace-server";
            a local compile leaves it None, so downloaders treat it as untrusted).
        ensembl_reference: Pinned reference id recorded in the manifest for reproducibility.
        log_files: Explicit run/provenance log files to record. If None, auto-discovers a top-level
            `*.log` plus per-role files under `spec_dir/logs/`. Logs are optional.
        provenance_file: Explicit structured-provenance document. If None, auto-discovers
            `spec_dir/provenance.json`. Optional; summarized into `manifest.provenance`.
        logo_file: Explicit module logo image. If None, auto-discovers `spec_dir/logo.{png,jpg,jpeg}`.
            Optional; hashed into `manifest.logo`, kept out of `artifact.digest`.
    """
    spec_dir = Path(spec_dir)
    output_dir = Path(output_dir)

    validation = validate_spec(spec_dir)
    if not validation.valid:
        return CompilationResult(
            success=False, errors=validation.errors, warnings=validation.warnings
        )

    config, _ = _load_yaml(spec_dir / "module_spec.yaml")
    assert config is not None
    variants, _, _ = _load_csv_rows(spec_dir / "variants.csv", VariantRow, "variants.csv")
    studies: list[StudyRow] = []
    if (spec_dir / "studies.csv").exists():
        studies, _, _ = _load_csv_rows(spec_dir / "studies.csv", StudyRow, "studies.csv")

    all_warnings = list(validation.warnings)
    if resolve_with_ensembl:
        from just_dna_compiler.resolver import resolve_variants

        variants, resolve_warnings = resolve_variants(variants, ensembl_cache)
        all_warnings.extend(resolve_warnings)

    module_name = config.module.name
    weights_df = _build_weights(variants, config)
    annotations_df = _build_annotations(variants, module_name)
    studies_df = _build_studies(studies, module_name) if studies else None

    output_dir.mkdir(parents=True, exist_ok=True)
    weights_df.write_parquet(output_dir / "weights.parquet", compression=compression)
    annotations_df.write_parquet(output_dir / "annotations.parquet", compression=compression)
    if studies_df is not None:
        studies_df.write_parquet(output_dir / "studies.parquet", compression=compression)

    logs = _collect_logs(spec_dir, output_dir, log_files)
    provenance = _collect_provenance(spec_dir, output_dir, provenance_file)
    logo = _collect_logo(spec_dir, output_dir, logo_file)
    manifest = _build_manifest(
        config=config,
        spec_dir=spec_dir,
        output_dir=output_dir,
        validation=validation,
        weights_rows=weights_df.height,
        warnings=all_warnings,
        compiled_by=compiled_by,
        ensembl_reference=ensembl_reference,
        logs=logs,
        provenance=provenance,
        logo=logo,
    )
    write_manifest(manifest, output_dir / "manifest.json")

    stats: dict[str, Any] = {
        "module_name": module_name,
        "weights_rows": weights_df.height,
        "annotations_rows": annotations_df.height,
        "studies_rows": studies_df.height if studies_df is not None else 0,
    }
    return CompilationResult(
        success=True,
        output_dir=output_dir,
        errors=[],
        warnings=all_warnings,
        stats=stats,
        manifest=manifest,
    )


def _build_manifest(
    *,
    config: ModuleSpecConfig,
    spec_dir: Path,
    output_dir: Path,
    validation: ValidationResult,
    weights_rows: int,
    warnings: list[str],
    compiled_by: Optional[str],
    ensembl_reference: Optional[str],
    logs: list[FileEntry],
    provenance: Optional[Provenance],
    logo: Optional[FileEntry],
) -> ModuleManifest:
    """Assemble the manifest from the spec, validation stats, and hashed input/output/log files."""
    module = config.module
    vstats = validation.stats
    return ModuleManifest(
        identity=Identity(name=module.name),
        display=Display(
            title=module.title,
            description=module.description,
            report_title=module.report_title,
            icon=module.icon,
            icon_set=module.icon_set,
            color=module.color,
        ),
        genome_build=config.genome_build,
        curator=config.defaults.curator,
        method=config.defaults.method,
        stats=Stats(
            variant_count=vstats.get("variant_count", 0),
            weights_rows=weights_rows,
            study_count=vstats.get("study_count", 0),
            gene_count=vstats.get("gene_count", 0),
            genes=vstats.get("genes", []),
            categories=vstats.get("categories", []),
            clinvar_count=vstats.get("clinvar_count", 0),
            pathogenic_count=vstats.get("pathogenic_count", 0),
            benign_count=vstats.get("benign_count", 0),
        ),
        compilation=Compilation(
            compile_success=True,
            compiled_by=compiled_by,
            compiler_version=_compiler_version(),
            ensembl_reference=ensembl_reference,
            compiled_at=_now_iso(),
            warnings=warnings,
        ),
        inputs=file_entries(spec_dir, list(_INPUT_FILES)),
        artifact=build_artifact(output_dir, list(_OUTPUT_FILES)),
        logs=logs,
        provenance=provenance,
        panel=config.panel,
        logo=logo,
    )


# ── Parquet builders ───────────────────────────────────────────────────────────


def _build_weights(variants: list[VariantRow], config: ModuleSpecConfig) -> pl.DataFrame:
    """Build the weights.parquet DataFrame from validated variant rows."""
    defaults = config.defaults
    module_name = config.module.name
    records: list[dict[str, Any]] = []
    for v in variants:
        priority = v.priority if v.priority is not None else defaults.priority
        records.append(
            {
                "rsid": v.rsid,
                "genotype": _split_genotype(v.genotype),
                # Phase bit: `genotype` is stored as an allele *list*, which cannot itself
                # distinguish a phased A|G from an unphased (sorted) A/G — both split to ["A","G"].
                # This flag preserves the distinction so the round-trip is lossless (ROADMAP 0.3 5b).
                "phased": "|" in v.genotype,
                "module": module_name,
                "weight": v.weight,
                "state": v.state,
                "priority": priority,
                "conclusion": v.conclusion,
                "negatives": v.negatives,
                "curator": v.curator or defaults.curator,
                "method": v.method or defaults.method,
                "chrom": v.chrom,
                "start": v.start,
                "end": v.start,
                "ref": v.ref,
                "alts": v.alts.split(",") if v.alts else None,
                "clinvar": v.clinvar if v.clinvar is not None else False,
                "pathogenic": v.pathogenic if v.pathogenic is not None else False,
                "benign": v.benign if v.benign is not None else False,
                "likely_pathogenic": False,
                "likely_benign": False,
                # ── 0.3 additive columns (materialized passthrough; derivations are NOT computed
                # here — see docs/COMPILER.md). ──
                "direction": v.direction,
                "stat_significance": v.stat_significance,
                "effect_size": v.effect_size,
                "effect_measure": v.effect_measure,
                "effect_allele": v.effect_allele,
                "flags": v.flags,
                "trait_efo_id": v.trait_efo_id,
                "clin_sig": v.clin_sig,
            }
        )
    schema = {
        "rsid": pl.Utf8,
        "genotype": pl.List(pl.Utf8),
        "phased": pl.Boolean,
        "module": pl.Utf8,
        "weight": pl.Float64,
        "state": pl.Utf8,
        "priority": pl.Utf8,
        "conclusion": pl.Utf8,
        "negatives": pl.Utf8,
        "curator": pl.Utf8,
        "method": pl.Utf8,
        "chrom": pl.Utf8,
        "start": pl.UInt32,
        "end": pl.UInt32,
        "ref": pl.Utf8,
        "alts": pl.List(pl.Utf8),
        "clinvar": pl.Boolean,
        "pathogenic": pl.Boolean,
        "benign": pl.Boolean,
        "likely_pathogenic": pl.Boolean,
        "likely_benign": pl.Boolean,
        "direction": pl.Utf8,
        "stat_significance": pl.Utf8,
        "effect_size": pl.Float64,
        "effect_measure": pl.Utf8,
        "effect_allele": pl.Utf8,
        "flags": pl.List(pl.Utf8),
        "trait_efo_id": pl.Utf8,
        "clin_sig": pl.Utf8,
    }
    return pl.DataFrame(records, schema=schema)


def _build_annotations(variants: list[VariantRow], module_name: str) -> pl.DataFrame:
    """Build annotations.parquet, deduplicated by variant_key (first occurrence wins)."""
    seen_keys: set[str] = set()
    records: list[dict[str, Optional[str]]] = []
    for v in variants:
        key = v.variant_key
        if key not in seen_keys:
            records.append(
                {
                    "rsid": v.rsid,
                    "module": module_name,
                    "gene": v.gene or "",
                    "phenotype": v.phenotype or "",
                    "category": v.category or "",
                }
            )
            seen_keys.add(key)
    schema = {
        "rsid": pl.Utf8,
        "module": pl.Utf8,
        "gene": pl.Utf8,
        "phenotype": pl.Utf8,
        "category": pl.Utf8,
    }
    return pl.DataFrame(records, schema=schema)


def _build_studies(studies: list[StudyRow], module_name: str) -> pl.DataFrame:
    """Build the studies.parquet DataFrame from validated study rows."""
    records: list[dict[str, Any]] = []
    for s in studies:
        records.append(
            {
                "rsid": s.rsid,
                "module": module_name,
                "pmid": s.pmid,
                "population": s.population,
                "p_value": s.p_value,
                "conclusion": s.conclusion,
                "study_design": s.study_design,
                # ── 0.3 additive columns (materialized passthrough). ──
                "stat_significance": s.stat_significance,
                "effect_size": s.effect_size,
                "effect_measure": s.effect_measure,
                "trait_efo_id": s.trait_efo_id,
            }
        )
    schema = {
        "rsid": pl.Utf8,
        "module": pl.Utf8,
        "pmid": pl.Utf8,
        "population": pl.Utf8,
        "p_value": pl.Utf8,
        "conclusion": pl.Utf8,
        "study_design": pl.Utf8,
        "stat_significance": pl.Utf8,
        "effect_size": pl.Float64,
        "effect_measure": pl.Utf8,
        "trait_efo_id": pl.Utf8,
    }
    return pl.DataFrame(records, schema=schema)


# ── Reverse engineering ────────────────────────────────────────────────────────


def reverse_module(
    parquet_dir: Path,
    output_dir: Path,
    module_name: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    report_title: Optional[str] = None,
    icon: str = "database",
    color: str = "#6435c9",
) -> Path:
    """Reverse-engineer a parquet module back into the spec DSL (yaml + csv). Returns output_dir."""
    parquet_dir = Path(parquet_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    weights_df = pl.read_parquet(parquet_dir / "weights.parquet")
    if module_name is None:
        if "module" in weights_df.columns:
            module_name = weights_df["module"].drop_nulls().unique().to_list()[0]
        else:
            module_name = parquet_dir.name

    default_curator = _most_common(weights_df, "curator") or "unknown"
    default_method = _most_common(weights_df, "method") or "unknown"
    default_priority: Optional[str] = None
    if "priority" in weights_df.columns:
        non_null = weights_df["priority"].drop_nulls()
        if non_null.len() > 0:
            default_priority = non_null.mode().to_list()[0]

    annotations_df: Optional[pl.DataFrame] = None
    ann_path = parquet_dir / "annotations.parquet"
    if ann_path.exists():
        annotations_df = pl.read_parquet(ann_path)

    defaults_dict: dict[str, Any] = {"curator": default_curator, "method": default_method}
    if default_priority is not None:
        defaults_dict["priority"] = default_priority

    spec = {
        "schema_version": "1.0",
        "module": {
            "name": module_name,
            "title": title or module_name.replace("_", " ").title(),
            "description": description or f"Annotation module: {module_name}",
            "report_title": report_title or module_name.replace("_", " ").title(),
            "icon": icon,
            "color": color,
        },
        "defaults": defaults_dict,
        "genome_build": "GRCh38",
    }
    (output_dir / "module_spec.yaml").write_text(
        yaml.dump(spec, default_flow_style=False, sort_keys=False), encoding="utf-8"
    )

    ann_lookup: dict[str, dict[str, str]] = {}
    if annotations_df is not None:
        for row in annotations_df.iter_rows(named=True):
            ann_lookup[row["rsid"]] = {
                "gene": row.get("gene", ""),
                "phenotype": row.get("phenotype", ""),
                "category": row.get("category", ""),
            }

    _write_variants_csv(
        weights_df, ann_lookup, default_curator, default_method, default_priority,
        output_dir / "variants.csv",
    )
    studies_path = parquet_dir / "studies.parquet"
    if studies_path.exists():
        _write_studies_csv(pl.read_parquet(studies_path), output_dir / "studies.csv")
    return output_dir


def _most_common(df: pl.DataFrame, col: str) -> Optional[str]:
    """Return the most common non-null value in a column, or None."""
    if col not in df.columns:
        return None
    non_null = df[col].drop_nulls()
    if non_null.len() == 0:
        return None
    return non_null.mode().to_list()[0]


def _write_variants_csv(
    weights_df: pl.DataFrame,
    ann_lookup: dict[str, dict[str, str]],
    default_curator: str,
    default_method: str,
    default_priority: Optional[str],
    output_path: Path,
) -> None:
    """Write variants.csv from weights parquet + annotations lookup."""
    fieldnames = [
        "rsid", "chrom", "start", "ref", "alts", "genotype", "weight", "state", "conclusion",
        "negatives", "priority", "gene", "phenotype", "category", "clinvar", "pathogenic", "benign",
        "curator", "method",
        # 0.3 additive columns
        "direction", "stat_significance", "effect_size", "effect_measure", "effect_allele",
        "flags", "trait_efo_id", "clin_sig",
    ]
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in weights_df.iter_rows(named=True):
            rsid = row.get("rsid") or ""
            ann = ann_lookup.get(rsid, {})
            genotype_list = row.get("genotype", [])
            alts_list = row.get("alts")
            curator = row.get("curator", "")
            method = row.get("method", "")
            priority = row.get("priority")
            clinvar = row.get("clinvar", False)
            pathogenic = row.get("pathogenic", False)
            benign = row.get("benign", False)
            # Reconstruct the genotype string. The `phased` bit (materialized alongside the allele
            # list) tells us which separator to re-emit: a phased pair keeps its order and joins with
            # '|'; an unphased pair is re-emitted alphabetically sorted with '/'; a single allele
            # (hemizygous / homoplasmic) passes through. Lossless round-trip (ROADMAP 0.3 item 5b).
            if genotype_list and len(genotype_list) == 2:
                if row.get("phased"):
                    genotype_str = "|".join(genotype_list)
                else:
                    genotype_str = "/".join(sorted(genotype_list))
            else:
                genotype_str = "/".join(genotype_list) if genotype_list else ""
            flags_list = row.get("flags")
            effect_size = row.get("effect_size")
            writer.writerow(
                {
                    "rsid": rsid,
                    "chrom": row.get("chrom", ""),
                    "start": row.get("start", ""),
                    "ref": row.get("ref", ""),
                    "alts": ",".join(alts_list) if alts_list else "",
                    "genotype": genotype_str,
                    "weight": row.get("weight") if row.get("weight") is not None else "",
                    "state": row.get("state", ""),
                    "conclusion": row.get("conclusion", ""),
                    "negatives": row.get("negatives") or "",
                    "priority": priority if priority != default_priority else "",
                    "gene": ann.get("gene", ""),
                    "phenotype": ann.get("phenotype", ""),
                    "category": ann.get("category", ""),
                    "clinvar": str(clinvar).lower() if clinvar else "",
                    "pathogenic": str(pathogenic).lower() if pathogenic else "",
                    "benign": str(benign).lower() if benign else "",
                    "curator": curator if curator != default_curator else "",
                    "method": method if method != default_method else "",
                    "direction": row.get("direction") or "",
                    "stat_significance": row.get("stat_significance") or "",
                    "effect_size": effect_size if effect_size is not None else "",
                    "effect_measure": row.get("effect_measure") or "",
                    "effect_allele": row.get("effect_allele") or "",
                    "flags": "|".join(flags_list) if flags_list else "",
                    "trait_efo_id": row.get("trait_efo_id") or "",
                    "clin_sig": row.get("clin_sig") or "",
                }
            )


def _write_studies_csv(studies_df: pl.DataFrame, output_path: Path) -> None:
    """Write studies.csv from studies parquet."""
    fieldnames = [
        "rsid", "pmid", "population", "p_value", "conclusion", "study_design",
        # 0.3 additive columns
        "stat_significance", "effect_size", "effect_measure", "trait_efo_id",
    ]
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in studies_df.iter_rows(named=True):
            pmid = row.get("pmid")
            if pmid is None or str(pmid).strip() == "":
                continue
            effect_size = row.get("effect_size")
            writer.writerow(
                {
                    "rsid": row["rsid"],
                    "pmid": str(pmid).strip(),
                    "population": row.get("population") or "",
                    "p_value": row.get("p_value") or "",
                    "conclusion": row.get("conclusion") or "",
                    "study_design": row.get("study_design") or "",
                    "stat_significance": row.get("stat_significance") or "",
                    "effect_size": effect_size if effect_size is not None else "",
                    "effect_measure": row.get("effect_measure") or "",
                    "trait_efo_id": row.get("trait_efo_id") or "",
                }
            )
