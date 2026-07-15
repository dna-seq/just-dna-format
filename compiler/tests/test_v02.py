"""0.2.0 additive features end-to-end through the compiler: ClinVar stats, structured provenance,
gene-panel passthrough, the `negatives` field, module logo, `icon_set`, and signed-manifest verify.

All run with resolve_with_ensembl=False (no reference/network needed)."""

import json
from pathlib import Path

import polars as pl
import pytest
from just_dna_format.integrity import IntegrityError, sha256_file, verify_manifest
from just_dna_format.manifest import read_manifest
from just_dna_format.signing import generate_private_key_pem, public_key_b64_from_pem, sign_digest

from just_dna_compiler.compiler import compile_module

_YAML = """\
schema_version: "1.0"
module:
  name: demo2
  title: Demo Two
  description: A demo module
  report_title: Demo Report
  icon: shield
  icon_set: awesome
  color: "#21ba45"
defaults:
  curator: tester
  method: manual
genome_build: GRCh38
panel:
  source: clinvar
  reference: "2026-06"
  reference_sha256: "sha256:deadbeef"
  genes: [BRCA1, BRCA2]
  significance: [pathogenic, likely_pathogenic]
"""

# Two clinvar rows, one pathogenic; one row carries `negatives`.
_VARIANTS = """\
rsid,chrom,start,ref,alts,genotype,weight,state,conclusion,negatives,gene,category,clinvar,pathogenic,benign
rs1801133,1,11856378,G,A,A/G,0.5,protective,ok,carries a trade-off,MTHFR,metabolism,true,false,false
rs7412,19,44908822,C,T,C/T,-0.3,risk,bad,,APOE,lipids,true,true,false
"""

_STUDIES = """\
rsid,pmid,population,p_value,conclusion,study_design
rs1801133,[PMID: 12345],EUR,0.01,assoc,GWAS
rs7412,67890,EUR,0.001,assoc,meta-analysis
"""

_PROVENANCE = {
    "generator": "agent-x",
    "model": "claude",
    "agent_version": "1.0",
    "items": [
        {"variant_key": "rs1801133", "rationale": "curated", "human_reviewed": True},
        {"variant_key": "rs7412", "confidence": 0.9},
    ],
}


def _write_spec(
    d: Path, *, provenance: bool = True, logo: bool = True
) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "module_spec.yaml").write_text(_YAML, encoding="utf-8")
    (d / "variants.csv").write_text(_VARIANTS, encoding="utf-8")
    (d / "studies.csv").write_text(_STUDIES, encoding="utf-8")
    if provenance:
        (d / "provenance.json").write_text(json.dumps(_PROVENANCE), encoding="utf-8")
    if logo:
        (d / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n fake-logo-bytes")
    return d


def _compile(spec: Path, out: Path):
    result = compile_module(spec, out, resolve_with_ensembl=False, compiled_by="marketplace-server")
    assert result.success, result.errors
    assert result.manifest is not None
    return result.manifest


def test_clinvar_stats_counts(tmp_path: Path) -> None:
    m = _compile(_write_spec(tmp_path / "s"), tmp_path / "o")
    assert m.stats.clinvar_count == 2
    assert m.stats.pathogenic_count == 1
    assert m.stats.benign_count == 0


def test_panel_passthrough_verbatim(tmp_path: Path) -> None:
    m = _compile(_write_spec(tmp_path / "s"), tmp_path / "o")
    assert m.panel is not None
    assert m.panel.source == "clinvar"
    assert m.panel.genes == ["BRCA1", "BRCA2"]
    assert m.panel.significance == ["pathogenic", "likely_pathogenic"]
    assert m.panel.reference_sha256 == "sha256:deadbeef"
    # Panel does not materialize variants: count still reflects only variants.csv.
    assert m.stats.variant_count == 2


def test_icon_set_flows_to_manifest(tmp_path: Path) -> None:
    m = _compile(_write_spec(tmp_path / "s"), tmp_path / "o")
    assert m.display.icon == "shield"
    assert m.display.icon_set == "awesome"


def test_negatives_lands_in_weights(tmp_path: Path) -> None:
    out = tmp_path / "o"
    _compile(_write_spec(tmp_path / "s"), out)
    weights = pl.read_parquet(out / "weights.parquet")
    assert "negatives" in weights.columns
    row = weights.filter(pl.col("rsid") == "rs1801133")
    assert row["negatives"].to_list() == ["carries a trade-off"]


def test_provenance_summary_and_hash(tmp_path: Path) -> None:
    out = tmp_path / "o"
    m = _compile(_write_spec(tmp_path / "s"), out)
    assert m.provenance is not None
    assert m.provenance.item_count == 2
    assert m.provenance.generator == "agent-x"
    assert m.provenance.file == "provenance.json"
    assert (out / "provenance.json").is_file()
    assert m.provenance.sha256 == sha256_file(out / "provenance.json")


def test_logo_hashed_and_shipped(tmp_path: Path) -> None:
    out = tmp_path / "o"
    m = _compile(_write_spec(tmp_path / "s"), out)
    assert m.logo is not None
    assert m.logo.name == "logo.png"
    assert (out / "logo.png").is_file()
    assert m.logo.sha256 == sha256_file(out / "logo.png")
    # Logo is NOT an artifact file (out of digest).
    assert "logo.png" not in {f.name for f in m.artifact.files}


def test_optional_files_do_not_change_digest(tmp_path: Path) -> None:
    full = _compile(_write_spec(tmp_path / "full"), tmp_path / "of")
    bare = _compile(
        _write_spec(tmp_path / "bare", provenance=False, logo=False), tmp_path / "ob"
    )
    # provenance.json + logo.png are out of artifact.digest → identical content identity.
    assert full.artifact.digest == bare.artifact.digest


def test_unsupported_logo_extension_rejected(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path / "s", logo=False)
    gif = spec / "logo.gif"
    gif.write_bytes(b"GIF89a")
    # An unsupported logo now surfaces as a compile error, not an uncaught exception.
    result = compile_module(spec, tmp_path / "o", resolve_with_ensembl=False, logo_file=gif)
    assert not result.success
    assert any("logo must be one of" in e for e in result.errors)


def test_verify_manifest_checks_optional_files(tmp_path: Path) -> None:
    out = tmp_path / "o"
    m = _compile(_write_spec(tmp_path / "s"), out)
    verify_manifest(out, m, check_logs=True, check_provenance=True, check_logo=True)

    (out / "provenance.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(IntegrityError, match="provenance hash mismatch"):
        verify_manifest(out, m, check_provenance=True)


def test_signed_manifest_verifies_with_pinned_key(tmp_path: Path) -> None:
    out = tmp_path / "o"
    m = _compile(_write_spec(tmp_path / "s"), out)
    pem = generate_private_key_pem()
    m.signature = sign_digest(m.artifact.digest, pem)

    verify_manifest(out, m, public_key=public_key_b64_from_pem(pem))
    with pytest.raises(IntegrityError, match="pinned"):
        verify_manifest(out, m, public_key=public_key_b64_from_pem(generate_private_key_pem()))


def test_pinned_key_but_unsigned_manifest_fails(tmp_path: Path) -> None:
    out = tmp_path / "o"
    m = _compile(_write_spec(tmp_path / "s"), out)
    with pytest.raises(IntegrityError, match="no signature"):
        verify_manifest(out, m, public_key=public_key_b64_from_pem(generate_private_key_pem()))
