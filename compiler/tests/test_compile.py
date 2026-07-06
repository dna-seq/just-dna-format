"""Compiler tests (SPEC §13): manifest emission, gene/category stats, and integrity round-trip.

All tests run with resolve_with_ensembl=False, so no Ensembl reference/network is needed. The
Ensembl-resolving path is integration-tested separately with real reference data.
"""

import hashlib
from pathlib import Path

import pytest
from just_dna_format.integrity import IntegrityError, verify_manifest
from just_dna_format.manifest import read_manifest

from just_dna_compiler.compiler import compile_module, validate_spec

_MODULE_YAML = """\
schema_version: "1.0"
module:
  name: demo_module
  title: Demo Module
  description: A demo module
  report_title: Demo Report
  icon: dna
  color: "#21ba45"
defaults:
  curator: tester
  method: manual
genome_build: GRCh38
"""

_VARIANTS_CSV = """\
rsid,chrom,start,ref,alts,genotype,weight,state,conclusion,gene,category
rs1801133,1,11856378,G,A,A/G,0.5,protective,ok,MTHFR,metabolism
rs7412,19,44908822,C,T,C/T,-0.3,risk,bad,APOE,lipids
"""

_STUDIES_CSV = """\
rsid,pmid,population,p_value,conclusion,study_design
rs1801133,12345,EUR,0.01,assoc,GWAS
rs7412,67890,EUR,0.001,assoc,meta-analysis
"""


@pytest.fixture
def spec_dir(tmp_path: Path) -> Path:
    (tmp_path / "module_spec.yaml").write_text(_MODULE_YAML, encoding="utf-8")
    (tmp_path / "variants.csv").write_text(_VARIANTS_CSV, encoding="utf-8")
    (tmp_path / "studies.csv").write_text(_STUDIES_CSV, encoding="utf-8")
    return tmp_path


def test_validate_spec_emits_gene_and_category_lists(spec_dir: Path) -> None:
    result = validate_spec(spec_dir)
    assert result.valid, result.errors
    assert result.stats["genes"] == ["APOE", "MTHFR"]        # sorted, None filtered
    assert result.stats["categories"] == ["lipids", "metabolism"]
    assert result.stats["variant_count"] == 2
    assert result.stats["gene_count"] == 2
    assert result.stats["study_count"] == 2


def test_validate_spec_requires_studies(tmp_path: Path) -> None:
    (tmp_path / "module_spec.yaml").write_text(_MODULE_YAML, encoding="utf-8")
    (tmp_path / "variants.csv").write_text(_VARIANTS_CSV, encoding="utf-8")
    result = validate_spec(tmp_path)
    assert not result.valid
    assert any("studies.csv is missing" in e for e in result.errors)


def test_compile_emits_parquets_and_manifest(spec_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    result = compile_module(spec_dir, out, resolve_with_ensembl=False)
    assert result.success, result.errors
    for name in ("weights.parquet", "annotations.parquet", "studies.parquet", "manifest.json"):
        assert (out / name).is_file(), f"missing {name}"

    manifest = result.manifest
    assert manifest is not None
    assert manifest.identity.name == "demo_module"
    assert manifest.stats.genes == ["APOE", "MTHFR"]
    assert manifest.stats.variant_count == 2
    assert manifest.stats.weights_rows == 2
    assert manifest.compilation.compile_success is True
    assert manifest.compilation.compiler_version.startswith("just-dna-compiler")
    assert {f.name for f in manifest.artifact.files} == {
        "weights.parquet", "annotations.parquet", "studies.parquet"
    }
    # The on-disk manifest matches the returned one.
    assert read_manifest(out / "manifest.json") == manifest


def test_input_hashes_match_hashlib(spec_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    manifest = compile_module(spec_dir, out, resolve_with_ensembl=False).manifest
    assert manifest is not None
    by_name = {i.name: i for i in manifest.inputs}
    for fname in ("module_spec.yaml", "variants.csv", "studies.csv"):
        expected = "sha256:" + hashlib.sha256((spec_dir / fname).read_bytes()).hexdigest()
        assert by_name[fname].sha256 == expected


def test_local_compile_is_untrusted_but_marketplace_compile_verifies(
    spec_dir: Path, tmp_path: Path
) -> None:
    # Local compile leaves compiled_by=None -> marketplace trust check rejects it.
    local = tmp_path / "local"
    compile_module(spec_dir, local, resolve_with_ensembl=False)
    manifest = read_manifest(local / "manifest.json")
    with pytest.raises(IntegrityError, match="untrusted"):
        verify_manifest(local, manifest)
    verify_manifest(local, manifest, require_marketplace=False)  # ok without the trust gate

    # A marketplace-tagged compile passes the full check.
    served = tmp_path / "served"
    compile_module(spec_dir, served, resolve_with_ensembl=False, compiled_by="marketplace-server")
    verify_manifest(served, read_manifest(served / "manifest.json"))


def test_tampered_parquet_fails_verification(spec_dir: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    compile_module(spec_dir, out, resolve_with_ensembl=False, compiled_by="marketplace-server")
    manifest = read_manifest(out / "manifest.json")
    (out / "weights.parquet").write_bytes(b"corrupted")
    with pytest.raises(IntegrityError):
        verify_manifest(out, manifest)
