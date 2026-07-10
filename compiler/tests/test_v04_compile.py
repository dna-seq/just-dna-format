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


# ── The remaining table kinds (pgs / copynumbers / heteroplasmy / activity / haplotypes /
# allele_function), previously covered only by the schema unit tests — now compiled + round-tripped
# so a regression in the generic materializer is caught here too. ────────────────────────────────

_QUANT_YAML = _YAML.replace("composed", "quant")
_ACTIVITY = (
    "gene,measure_kind,measure_min,measure_max,phenotype,conclusion,unresolved\n"
    "CYP2D6,activity_score,0,0,Poor Metabolizer,AS 0 — PM,false\n"
    "CYP2D6,activity_score,0.25,1.0,Intermediate Metabolizer,AS 0.25–1 — IM,false\n"
    "CYP2D6,activity_score,,,,activity score not computable,true\n"
)
_COPYNUMBERS = (
    "gene,measure_kind,measure_min,measure_max,modifier_gene,modifier_cn,"
    "direction,clin_sig,phenotype,trait_efo_id,conclusion,unresolved\n"
    "SMN1,copy_number,0,0,SMN2,3,risk,pathogenic,SMA,MONDO_0011226,0 SMN1 / 3 SMN2,false\n"
    "SMN1,copy_number,1,1,,,risk,,SMA,MONDO_0011226,1 copy — carrier,false\n"
    "SMN1,copy_number,,,,,,,,,seg-dup not resolved (~20x),true\n"
)
_HETEROPLASMY = (
    "gene,reference_sequence,tissue,measure_kind,measure_min,measure_max,"
    "direction,clin_sig,phenotype,trait_efo_id,conclusion,unresolved\n"
    "MT-TL1,NC_012920.1,blood,allele_fraction,0.6,1.0,risk,pathogenic,MELAS,MONDO_0010789,high burden,false\n"
    "MT-TL1,NC_012920.1,blood,allele_fraction,,,,,,,not called,true\n"
)
_HAPLOTYPES = (
    "haplotype_name,rsid,allele,gene\n"
    "*4,rs3892097,A,CYP2D6\n"
    "*10,rs1065852,T,CYP2D6\n"
)
_ALLELE_FUNCTION = (
    "gene,allele,activity_value,function_status\n"
    "CYP2D6,*1,1.0,normal_function\n"
    "CYP2D6,*4,0.0,no_function\n"
    "CYP2D6,*10,0.25,decreased_function\n"
)
_PGS = (
    "pgs_id,trait_efo_id,training_ancestry,training_cohort,match_rate_floor,research_tier,note\n"
    "PGS000135,EFO_0001645,EUR|EAS,UK Biobank,0.8,research_only,CAD score\n"
)

_QUANT_PARQUETS = (
    "activity_phenotype.parquet", "copynumbers.parquet", "heteroplasmy.parquet",
    "haplotypes.parquet", "allele_function.parquet", "pgs.parquet",
)


def _write_quant(d: Path) -> Path:
    """A variant-free module exercising the six remaining table kinds (RM2 composition)."""
    d.mkdir(parents=True, exist_ok=True)
    (d / "module_spec.yaml").write_text(_QUANT_YAML, encoding="utf-8")
    (d / "activity_phenotype.csv").write_text(_ACTIVITY, encoding="utf-8")
    (d / "copynumbers.csv").write_text(_COPYNUMBERS, encoding="utf-8")
    (d / "heteroplasmy.csv").write_text(_HETEROPLASMY, encoding="utf-8")
    (d / "haplotypes.csv").write_text(_HAPLOTYPES, encoding="utf-8")
    (d / "allele_function.csv").write_text(_ALLELE_FUNCTION, encoding="utf-8")
    (d / "pgs.csv").write_text(_PGS, encoding="utf-8")
    return d


def test_quant_module_materializes_and_roundtrips(tmp_path: Path) -> None:
    result = compile_module(_write_quant(tmp_path / "spec"), tmp_path / "orig", resolve_with_ensembl=False)
    assert result.success, result.errors
    for name in _QUANT_PARQUETS:
        assert (tmp_path / "orig" / name).is_file(), f"missing {name}"

    # pgs list-field survives the round to parquet as List(Utf8)
    pgs = pl.read_parquet(tmp_path / "orig" / "pgs.parquet").row(0, named=True)
    assert pgs["training_ancestry"] == ["EUR", "EAS"] and pgs["match_rate_floor"] == 0.8

    reverse_module(tmp_path / "orig", tmp_path / "reversed")
    rev = validate_spec(tmp_path / "reversed")
    assert rev.valid, rev.errors
    compile_module(tmp_path / "reversed", tmp_path / "recompiled", resolve_with_ensembl=False)
    for name in _QUANT_PARQUETS:
        orig = pl.read_parquet(tmp_path / "orig" / name)
        recompiled = pl.read_parquet(tmp_path / "recompiled" / name)
        assert orig.equals(recompiled), f"round-trip changed {name}"


def test_quant_digest_is_idempotent(tmp_path: Path) -> None:
    spec = _write_quant(tmp_path / "spec")
    a = compile_module(spec, tmp_path / "a", resolve_with_ensembl=False)
    b = compile_module(spec, tmp_path / "b", resolve_with_ensembl=False)
    assert a.manifest.artifact.digest == b.manifest.artifact.digest


def test_integer_counts_reverse_without_trailing_zero(tmp_path: Path) -> None:
    """A copy number / repeat count is a float `measure_min/max` in the model but must reverse to a
    bare int in the human-authorable CSV (36, not 36.0)."""
    import csv as _csv

    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "module_spec.yaml").write_text(_YAML.replace("composed", "reptest"), encoding="utf-8")
    (spec / "repeat_alleles.csv").write_text(
        "gene,repeat_unit,measure_kind,measure_min,measure_max,conclusion,unresolved\n"
        "HTT,CAG,repeat_count,36,39,reduced penetrance,false\n",
        encoding="utf-8",
    )
    compile_module(spec, tmp_path / "orig", resolve_with_ensembl=False)
    reverse_module(tmp_path / "orig", tmp_path / "reversed")
    with open(tmp_path / "reversed" / "repeat_alleles.csv", encoding="utf-8") as handle:
        row = next(_csv.DictReader(handle))
    assert row["measure_min"] == "36" and row["measure_max"] == "39"


# ── Table-level coherence is now enforced by the compiler (was schema-only). ─────────────────────


def _repeat_module(tmp_path: Path, body: str, name: str = "cohere") -> Path:
    spec = tmp_path / name
    spec.mkdir()
    (spec / "module_spec.yaml").write_text(_YAML.replace("composed", name), encoding="utf-8")
    (spec / "repeat_alleles.csv").write_text(
        "gene,repeat_unit,measure_kind,measure_min,measure_max,trait_efo_id,conclusion,unresolved\n" + body,
        encoding="utf-8",
    )
    return spec


def test_overlapping_bins_rejected(tmp_path: Path) -> None:
    spec = _repeat_module(
        tmp_path,
        "HTT,CAG,repeat_count,30,40,MONDO_0007739,a,false\n"
        "HTT,CAG,repeat_count,35,45,MONDO_0007739,b,false\n",
    )
    result = validate_spec(spec)
    assert not result.valid
    assert any("overlapping bins" in e for e in result.errors), result.errors


def test_bin_coverage_gap_warns(tmp_path: Path) -> None:
    spec = _repeat_module(
        tmp_path,
        "HTT,CAG,repeat_count,27,35,MONDO_0007739,a,false\n"
        "HTT,CAG,repeat_count,40,45,MONDO_0007739,b,false\n",
    )
    result = validate_spec(spec)
    assert result.valid, result.errors  # a gap is a warning, not an error
    assert any("coverage gap" in w for w in result.warnings), result.warnings


def test_multiple_unresolved_sentinels_rejected(tmp_path: Path) -> None:
    spec = _repeat_module(
        tmp_path,
        "HTT,CAG,repeat_count,,,MONDO_0007739,first sentinel,true\n"
        "HTT,CAG,repeat_count,,,MONDO_0007739,second sentinel,true\n",
    )
    result = validate_spec(spec)
    assert not result.valid
    assert any("unresolved sentinel" in e for e in result.errors), result.errors


def test_duplicate_diplotype_rejected(tmp_path: Path) -> None:
    spec = tmp_path / "dup"
    spec.mkdir()
    (spec / "module_spec.yaml").write_text(_YAML.replace("composed", "dup"), encoding="utf-8")
    # (*4,*1) canonicalizes to (*1,*4) — the same key as (*1,*4), so these two rows collide.
    (spec / "diplotypes.csv").write_text(
        "gene,haplotype_a,haplotype_b,phenotype,conclusion\n"
        "CYP2D6,*1,*4,IM,first\n"
        "CYP2D6,*4,*1,IM,dup after canonicalization\n",
        encoding="utf-8",
    )
    result = validate_spec(spec)
    assert not result.valid
    assert any("duplicate row" in e for e in result.errors), result.errors
