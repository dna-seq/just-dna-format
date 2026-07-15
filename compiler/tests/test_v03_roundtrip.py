"""0.3 round-trip fidelity, idempotency, and the non-diploid guardrail (CONSTITUTION Principle 7 +
ROADMAP item 5b). Proves the two invariants the earlier 0.3 ship deferred:

  * `reverse_module` → recompile preserves every 0.3 column INCLUDING phase (`A|G` vs sorted `A/G`);
  * compiling the same spec twice yields the same `artifact.digest`.

Plus the widened guardrail: a two-allele genotype warns on MT *and* Y, but not on X (diploid in XX).
All run with resolve_with_ensembl=False (no reference/network)."""

import csv
from pathlib import Path

import polars as pl
from just_dna_compiler.compiler import compile_module, reverse_module, validate_spec

_YAML = """\
schema_version: "1.0"
module:
  name: demo3rt
  title: Demo 0.3 Round-trip
  description: Round-trip fixture
  report_title: Demo Report
  color: "#21ba45"
defaults:
  curator: tester
  method: manual
genome_build: GRCh38
"""

# rs1 unphased sorted; rs2 PHASED and deliberately NOT alphabetical (T|C) to prove order survives;
# rs3 a single-allele hemizygous call. Every 0.3 column is populated.
_VARIANTS = """\
rsid,genotype,weight,state,conclusion,direction,stat_significance,effect_size,effect_measure,effect_allele,flags,trait_efo_id,clin_sig
rs1801133,A/G,0.5,protective,ok,protective,significant,0.6,OR,A,conditional|curated,EFO_0004518,likely_benign
rs429358,T|C,-0.3,risk,bad,risk,suggestive,3.2,OR,C,phased|pleiotropic,MONDO:0005265,pathogenic
rs7412,A,0.1,neutral,mid,neutral,not_significant,,,,,,
"""

_STUDIES = """\
rsid,pmid,population,p_value,conclusion,study_design,stat_significance,effect_size,effect_measure,trait_efo_id
rs1801133,12345,EUR,0.01,assoc,GWAS,significant,0.6,OR,EFO_0004518
rs429358,67890,EUR,0.001,assoc,meta-analysis,suggestive,3.2,OR,MONDO:0005265
rs7412,11111,EUR,0.5,none,GWAS,not_significant,,,
"""


def _write_spec(d: Path, variants: str = _VARIANTS, studies: str = _STUDIES) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "module_spec.yaml").write_text(_YAML, encoding="utf-8")
    (d / "variants.csv").write_text(variants, encoding="utf-8")
    (d / "studies.csv").write_text(studies, encoding="utf-8")
    return d


def test_roundtrip_is_lossless_including_phase(tmp_path: Path) -> None:
    compile_module(_write_spec(tmp_path / "spec"), tmp_path / "orig", resolve_with_ensembl=False)
    reverse_module(tmp_path / "orig", tmp_path / "reversed")
    assert validate_spec(tmp_path / "reversed").valid
    compile_module(tmp_path / "reversed", tmp_path / "recompiled", resolve_with_ensembl=False)

    orig_w = pl.read_parquet(tmp_path / "orig" / "weights.parquet")
    recomp_w = pl.read_parquet(tmp_path / "recompiled" / "weights.parquet")
    orig_s = pl.read_parquet(tmp_path / "orig" / "studies.parquet")
    recomp_s = pl.read_parquet(tmp_path / "recompiled" / "studies.parquet")

    # Every column of both artifacts survives the reverse→recompile round-trip unchanged.
    assert orig_w.equals(recomp_w)
    assert orig_s.equals(recomp_s)


def test_authoring_row_order_is_preserved(tmp_path: Path) -> None:
    """Row order survives compile → reverse → recompile. This is load-bearing, not cosmetic: parquet
    bytes depend on row order, so `artifact.digest` is order-sensitive (Principle 7 idempotency).
    Authored in a deliberately non-alphabetical rsid order to catch any accidental sorting."""
    variants = (
        "rsid,genotype,weight,state,conclusion\n"
        "rs7412,A,0.1,neutral,third\n"
        "rs1801133,A/G,0.5,protective,first\n"
        "rs429358,C,-0.3,risk,second\n"
    )
    studies = (
        "rsid,pmid\nrs7412,111\nrs1801133,222\nrs429358,333\n"
    )
    expected = ["rs7412", "rs1801133", "rs429358"]

    compile_module(
        _write_spec(tmp_path / "spec", variants, studies), tmp_path / "orig",
        resolve_with_ensembl=False,
    )
    assert pl.read_parquet(tmp_path / "orig" / "weights.parquet")["rsid"].to_list() == expected

    reverse_module(tmp_path / "orig", tmp_path / "reversed")
    reversed_rows = list(
        csv.DictReader((tmp_path / "reversed" / "variants.csv").read_text().splitlines())
    )
    assert [r["rsid"] for r in reversed_rows] == expected

    compile_module(tmp_path / "reversed", tmp_path / "recompiled", resolve_with_ensembl=False)
    assert pl.read_parquet(tmp_path / "recompiled" / "weights.parquet")["rsid"].to_list() == expected


def test_phase_bit_distinguishes_phased_from_unphased(tmp_path: Path) -> None:
    compile_module(_write_spec(tmp_path / "spec"), tmp_path / "out", resolve_with_ensembl=False)
    w = pl.read_parquet(tmp_path / "out" / "weights.parquet")
    by_rsid = {r["rsid"]: r for r in w.iter_rows(named=True)}

    # Phased row keeps its (non-alphabetical) allele order and is flagged phased.
    assert by_rsid["rs429358"]["genotype"] == ["T", "C"]
    assert by_rsid["rs429358"]["phased"] is True
    # Unphased row is sorted and not phased; single-allele hemizygous row is a 1-element list.
    assert by_rsid["rs1801133"]["genotype"] == ["A", "G"]
    assert by_rsid["rs1801133"]["phased"] is False
    assert by_rsid["rs7412"]["genotype"] == ["A"]
    assert by_rsid["rs7412"]["phased"] is False

    # And the reversed spec re-emits the phase separator verbatim.
    reverse_module(tmp_path / "out", tmp_path / "reversed")
    variants_csv = (tmp_path / "reversed" / "variants.csv").read_text(encoding="utf-8")
    assert "T|C" in variants_csv  # phased, order preserved
    assert "A/G" in variants_csv  # unphased, sorted


def test_recompile_digest_is_idempotent(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path / "spec")
    a = compile_module(spec, tmp_path / "a", resolve_with_ensembl=False)
    b = compile_module(spec, tmp_path / "b", resolve_with_ensembl=False)
    assert a.manifest is not None and b.manifest is not None
    assert a.manifest.artifact.digest == b.manifest.artifact.digest


# ── Non-diploid guardrail: MT and Y warn; X does not (ROADMAP item 5b) ───────────
_Y_VARIANT = """\
rsid,chrom,start,ref,genotype,weight,state,conclusion
rs99999,Y,2787000,A,A/G,0.0,neutral,two-allele Y is a fake diploid
"""
_X_VARIANT = """\
rsid,chrom,start,ref,genotype,weight,state,conclusion
rs88888,X,150000000,A,A/G,0.0,neutral,two-allele X is legitimate in XX
"""
_Y_HEMIZYGOUS = """\
rsid,chrom,start,ref,genotype,weight,state,conclusion
rs99999,Y,2787000,A,A,0.0,neutral,hemizygous Y single allele
"""
_Y_STUDY = "rsid,pmid\nrs99999,12345\n"
_X_STUDY = "rsid,pmid\nrs88888,12345\n"


def _diploid_warnings(result_warnings: list[str]) -> list[str]:
    return [w for w in result_warnings if "is not diploid" in w]


def test_two_allele_Y_warns(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path / "y", variants=_Y_VARIANT, studies=_Y_STUDY)
    warns = _diploid_warnings(validate_spec(spec).warnings)
    assert len(warns) == 1 and "chrom=Y" in warns[0]


def test_hemizygous_Y_does_not_warn(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path / "yh", variants=_Y_HEMIZYGOUS, studies=_Y_STUDY)
    assert _diploid_warnings(validate_spec(spec).warnings) == []


def test_two_allele_X_does_not_warn(tmp_path: Path) -> None:
    # X is diploid in XX samples — a two-allele X row is legitimate, so no false-positive warning.
    spec = _write_spec(tmp_path / "x", variants=_X_VARIANT, studies=_X_STUDY)
    assert _diploid_warnings(validate_spec(spec).warnings) == []
