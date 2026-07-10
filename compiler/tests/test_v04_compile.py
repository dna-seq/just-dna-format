"""0.4 compiler materialization (RM1) + composed / optional-table-kind modules (RM2).

Proves the new table kinds compile to parquet, round-trip losslessly (Principle 7), keep the digest
deterministic, and that a module composes from only the kinds it uses — including a module with NO
`variants.csv` (the composition principle). Mirrors `test_v03_roundtrip.py`'s inline-fixture idiom.
"""

from pathlib import Path

import polars as pl

from just_dna_compiler.compiler import compile_module, reverse_module, validate_spec

_YAML = (
    "schema_version: '1.0'\n"
    "module:\n"
    "  name: composed\n"
    "  title: Composed\n"
    "  description: A composed 0.4 module\n"
    "  report_title: Composed\n"
)
_VARIANTS = (
    "rsid,genotype,state,conclusion,gene,clin_sig,requires_callable,acmg_sf,actionability\n"
    "rs80357906,A/AT,risk,BRCA1 frameshift,BRCA1,pathogenic,true,true,preventable\n"
)
_STUDIES = "rsid,pmid\nrs80357906,29165669\n"
_REPEAT = (
    "gene,repeat_unit,source_field,measure_kind,measure_min,measure_max,"
    "direction,clin_sig,phenotype,trait_efo_id,conclusion,unresolved\n"
    "HTT,CAG,REPCN,repeat_count,40,,risk,pathogenic,HD,MONDO_0007739,>=40 CAG,false\n"
    "HTT,CAG,REPCN,repeat_count,,,,,,,not spanned (CI),true\n"
)
_DIPLOTYPES = (
    "gene,haplotype_a,haplotype_b,phenotype,conclusion,drug,response,evidence_level\n"
    "CYP2D6,*1,*4,IM,reduced codeine activation,codeine,reduced analgesia,1A\n"
)
_PHARM = (
    "rsid,gene,drug,response,evidence_level,conclusion\n"
    "rs9923231,VKORC1,warfarin,reduced dose requirement,1A,lower warfarin dose\n"
)

# The parquet kinds the composed fixture materializes.
_COMPOSED_PARQUETS = (
    "weights.parquet", "annotations.parquet", "studies.parquet",
    "repeat_alleles.parquet", "diplotypes.parquet", "pharm_variants.parquet",
)


def _write_composed(d: Path) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "module_spec.yaml").write_text(_YAML, encoding="utf-8")
    (d / "variants.csv").write_text(_VARIANTS, encoding="utf-8")
    (d / "studies.csv").write_text(_STUDIES, encoding="utf-8")
    (d / "repeat_alleles.csv").write_text(_REPEAT, encoding="utf-8")
    (d / "diplotypes.csv").write_text(_DIPLOTYPES, encoding="utf-8")
    (d / "pharm_variants.csv").write_text(_PHARM, encoding="utf-8")
    return d


def test_composed_module_materializes_all_kinds(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = compile_module(_write_composed(tmp_path / "spec"), out, resolve_with_ensembl=False)
    assert result.success, result.errors
    for name in _COMPOSED_PARQUETS:
        assert (out / name).is_file(), f"missing {name}"
    # the new parquets are in the content identity
    assert set(_COMPOSED_PARQUETS) <= {f.name for f in result.manifest.artifact.files}

    # weights carries the 3 new general axes
    w = pl.read_parquet(out / "weights.parquet").row(0, named=True)
    assert w["requires_callable"] is True and w["acmg_sf"] is True
    assert w["actionability"] == "preventable"

    # a binning row + the mandatory unresolved sentinel
    repeats = pl.read_parquet(out / "repeat_alleles.parquet")
    full = repeats.filter(pl.col("measure_min") == 40).row(0, named=True)
    assert full["measure_kind"] == "repeat_count" and full["source_field"] == "REPCN"
    assert full["measure_max"] is None and full["unresolved"] is False
    assert repeats.filter(pl.col("unresolved")).height == 1

    # diplotype pharm columns + single-variant pharm table
    dip = pl.read_parquet(out / "diplotypes.parquet").row(0, named=True)
    assert dip["drug"] == "codeine" and dip["evidence_level"] == "1A"
    ph = pl.read_parquet(out / "pharm_variants.parquet").row(0, named=True)
    assert ph["drug"] == "warfarin" and ph["evidence_level"] == "1A"


def test_composed_roundtrip_is_lossless(tmp_path: Path) -> None:
    compile_module(_write_composed(tmp_path / "spec"), tmp_path / "orig", resolve_with_ensembl=False)
    reverse_module(tmp_path / "orig", tmp_path / "reversed")
    assert validate_spec(tmp_path / "reversed").valid, validate_spec(tmp_path / "reversed").errors
    compile_module(tmp_path / "reversed", tmp_path / "recompiled", resolve_with_ensembl=False)
    for name in _COMPOSED_PARQUETS:
        orig = pl.read_parquet(tmp_path / "orig" / name)
        recompiled = pl.read_parquet(tmp_path / "recompiled" / name)
        assert orig.equals(recompiled), f"round-trip changed {name}"


def test_composed_digest_is_idempotent(tmp_path: Path) -> None:
    spec = _write_composed(tmp_path / "spec")
    a = compile_module(spec, tmp_path / "a", resolve_with_ensembl=False)
    b = compile_module(spec, tmp_path / "b", resolve_with_ensembl=False)
    assert a.manifest.artifact.digest == b.manifest.artifact.digest


def _write_pharm_only(d: Path) -> Path:
    """A module with NO variants.csv / studies.csv — only module_spec + pharm_variants (RM2)."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "module_spec.yaml").write_text(_YAML.replace("composed", "pharm_only"), encoding="utf-8")
    (d / "pharm_variants.csv").write_text(_PHARM, encoding="utf-8")
    return d


def test_pharm_only_module_composes_without_variants(tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = compile_module(_write_pharm_only(tmp_path / "spec"), out, resolve_with_ensembl=False)
    assert result.success, result.errors
    assert (out / "pharm_variants.parquet").is_file()
    # no SNP core: no weights/annotations/studies parquets
    assert not (out / "weights.parquet").exists()
    assert not (out / "studies.parquet").exists()
    assert {f.name for f in result.manifest.artifact.files} == {"pharm_variants.parquet"}


def test_pharm_only_module_roundtrips_without_variants(tmp_path: Path) -> None:
    compile_module(_write_pharm_only(tmp_path / "spec"), tmp_path / "orig", resolve_with_ensembl=False)
    reverse_module(tmp_path / "orig", tmp_path / "reversed")
    reversed_dir = tmp_path / "reversed"
    # reconstructs identity + its one table, and does NOT fabricate an empty variants.csv
    assert (reversed_dir / "module_spec.yaml").is_file()
    assert (reversed_dir / "pharm_variants.csv").is_file()
    assert not (reversed_dir / "variants.csv").exists()
    assert validate_spec(reversed_dir).valid, validate_spec(reversed_dir).errors
    compile_module(reversed_dir, tmp_path / "recompiled", resolve_with_ensembl=False)
    orig = pl.read_parquet(tmp_path / "orig" / "pharm_variants.parquet")
    recompiled = pl.read_parquet(tmp_path / "recompiled" / "pharm_variants.parquet")
    assert orig.equals(recompiled)
