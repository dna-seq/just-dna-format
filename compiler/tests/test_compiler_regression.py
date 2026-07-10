"""
Compiler regression tests ported from just-dna-lite's `test_module_compiler.py` and
`test_module_roundtrip.py`, made self-contained (no eval-data or network dependency): validation
error handling, output structure, and a reverse→recompile round-trip.

The Ensembl-resolution half lives in `test_resolver_integration.py` (skipped without a cache).
"""

from pathlib import Path

import polars as pl
import pytest
import yaml

from just_dna_compiler.compiler import compile_module, reverse_module, validate_spec

_MODULE_YAML = {
    "schema_version": "1.0",
    "module": {"name": "test_mod", "title": "Test", "description": "D", "report_title": "R"},
}

# A self-contained CYP-like spec: every row carries both rsid and position, so
# resolve_with_ensembl=False is a no-op and the core pipeline is exercised offline.
_VARIANTS_CSV = (
    "rsid,chrom,start,ref,alts,genotype,weight,state,conclusion,gene,phenotype,category\n"
    "rs4244285,10,94781859,G,A,A/G,-0.8,risk,CYP2C19*2 het,CYP2C19,Drug metabolism,cyp2c19\n"
    "rs4244285,10,94781859,G,A,G/G,0.0,neutral,Normal,CYP2C19,Drug metabolism,cyp2c19\n"
    "rs1057910,10,94981296,A,C,A/C,-0.6,significant,CYP2C9*3 het,CYP2C9,Warfarin,cyp2c9\n"
)
_STUDIES_CSV = (
    "rsid,pmid,population,p_value,conclusion,study_design\n"
    "rs4244285,123456,Test,0.05,Grounding evidence,Unit test\n"
    "rs1057910,7890,Test,0.01,Grounding,Unit test\n"
)


def _write_spec(directory: Path, variants: str = _VARIANTS_CSV, studies: str | None = _STUDIES_CSV) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "module_spec.yaml").write_text(yaml.dump(_MODULE_YAML), encoding="utf-8")
    (directory / "variants.csv").write_text(variants, encoding="utf-8")
    if studies is not None:
        (directory / "studies.csv").write_text(studies, encoding="utf-8")
    return directory


# ── Validation error handling ────────────────────────────────────────────────


def test_validate_nonexistent_dir() -> None:
    result = validate_spec(Path("/nonexistent/path"))
    assert not result.valid
    assert any("does not exist" in e for e in result.errors)


def test_validate_empty_dir(tmp_path: Path) -> None:
    result = validate_spec(tmp_path)
    assert not result.valid
    assert any("module_spec.yaml not found" in e for e in result.errors)


def test_validate_no_table_kind_rejected(tmp_path: Path) -> None:
    # variants.csv is optional now (RM2 composition), but a module with NO recognized table kind
    # (only module_spec.yaml here) is still rejected.
    (tmp_path / "module_spec.yaml").write_text(yaml.dump(_MODULE_YAML))
    result = validate_spec(tmp_path)
    assert not result.valid
    assert any("no recognized table" in e for e in result.errors)


def test_validate_malformed_row(tmp_path: Path) -> None:
    (tmp_path / "module_spec.yaml").write_text(yaml.dump(_MODULE_YAML))
    (tmp_path / "variants.csv").write_text(
        "rsid,genotype,weight,state,conclusion\nrs123,A/G,0.5,invalid_state,C\n"
    )
    result = validate_spec(tmp_path)
    assert not result.valid
    assert any("state" in e for e in result.errors)


def test_validate_duplicate_genotype(tmp_path: Path) -> None:
    (tmp_path / "module_spec.yaml").write_text(yaml.dump(_MODULE_YAML))
    (tmp_path / "variants.csv").write_text(
        "rsid,genotype,weight,state,conclusion\n"
        "rs123,A/G,0.5,risk,C\nrs123,A/G,-0.3,protective,Other\n"
    )
    result = validate_spec(tmp_path)
    assert not result.valid
    assert any("Duplicate" in e for e in result.errors)


def test_validate_weight_direction_warning(tmp_path: Path) -> None:
    (tmp_path / "module_spec.yaml").write_text(yaml.dump(_MODULE_YAML))
    (tmp_path / "variants.csv").write_text(
        "rsid,genotype,weight,state,conclusion\nrs123,A/G,0.5,risk,C\n"
    )
    (tmp_path / "studies.csv").write_text(
        "rsid,pmid,population,p_value,conclusion,study_design\nrs123,123456,T,0.05,E,U\n"
    )
    result = validate_spec(tmp_path)
    assert result.valid
    assert any("risk" in w and "weight=0.5" in w for w in result.warnings)


# ── Output structure ─────────────────────────────────────────────────────────


def test_weights_schema_and_dtypes(tmp_path: Path) -> None:
    compile_module(_write_spec(tmp_path / "spec"), tmp_path / "out", resolve_with_ensembl=False)
    df = pl.read_parquet(tmp_path / "out" / "weights.parquet")
    required = {
        "rsid", "genotype", "weight", "state", "conclusion", "priority", "module",
        "curator", "method", "clinvar", "pathogenic", "benign",
        "likely_pathogenic", "likely_benign", "alts",
    }
    assert required.issubset(set(df.columns))
    assert df.schema["genotype"] == pl.List(pl.Utf8)
    assert df.schema["weight"] == pl.Float64
    assert df.schema["clinvar"] == pl.Boolean
    assert df.schema["alts"] == pl.List(pl.Utf8)


def test_annotations_deduplicated_by_rsid(tmp_path: Path) -> None:
    compile_module(_write_spec(tmp_path / "spec"), tmp_path / "out", resolve_with_ensembl=False)
    ann = pl.read_parquet(tmp_path / "out" / "annotations.parquet")
    assert ann.height == ann["rsid"].n_unique()          # two rs4244285 rows collapse to one
    assert set(ann["category"].to_list()) == {"cyp2c19", "cyp2c9"}


def test_studies_rsids_subset_of_weights(tmp_path: Path) -> None:
    compile_module(_write_spec(tmp_path / "spec"), tmp_path / "out", resolve_with_ensembl=False)
    studies = set(pl.read_parquet(tmp_path / "out" / "studies.parquet")["rsid"].to_list())
    weights = set(pl.read_parquet(tmp_path / "out" / "weights.parquet")["rsid"].to_list())
    assert studies.issubset(weights)


def test_missing_studies_rejected(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path / "spec", studies=None)
    result = compile_module(spec, tmp_path / "out", resolve_with_ensembl=False)
    assert not result.success
    assert any("studies.csv is missing" in e for e in result.errors)


def test_compile_nonexistent_dir_fails(tmp_path: Path) -> None:
    result = compile_module(Path("/nonexistent"), tmp_path / "out", resolve_with_ensembl=False)
    assert not result.success and result.errors


def test_no_resolve_flag_leaves_positions(tmp_path: Path) -> None:
    spec = _write_spec(
        tmp_path / "spec",
        variants="rsid,genotype,weight,state,conclusion\nrs4244285,A/G,0.0,neutral,Test\n",
    )
    compile_module(spec, tmp_path / "out", resolve_with_ensembl=False)
    df = pl.read_parquet(tmp_path / "out" / "weights.parquet")
    assert df["chrom"][0] is None and df["start"][0] is None


# ── Reverse → recompile round-trip (self-contained; replaces the HF-download test) ──


def test_reverse_recompile_roundtrip_preserves_data(tmp_path: Path) -> None:
    # Compile once to get a canonical parquet "original".
    compile_module(_write_spec(tmp_path / "spec"), tmp_path / "orig", resolve_with_ensembl=False)
    # Reverse the parquet artifact back into a spec DSL, then recompile it.
    reverse_module(tmp_path / "orig", tmp_path / "reversed", module_name="test_mod")
    assert validate_spec(tmp_path / "reversed").valid
    compile_module(tmp_path / "reversed", tmp_path / "recompiled", resolve_with_ensembl=False)

    orig = pl.read_parquet(tmp_path / "orig" / "weights.parquet")
    recomp = pl.read_parquet(tmp_path / "recompiled" / "weights.parquet")

    def keys(df: pl.DataFrame) -> set[str]:
        return {f"{r[0]}:{'/'.join(r[1])}" for r in df.select('rsid', 'genotype').iter_rows()}

    assert keys(orig) == keys(recomp)                                    # (rsid, genotype) set
    assert set(orig["rsid"].to_list()) == set(recomp["rsid"].to_list())  # rsid set
    weights = {r[0]: r[1] for r in recomp.select("conclusion", "weight").iter_rows()}
    assert weights["CYP2C19*2 het"] == -0.8                              # weights survive
