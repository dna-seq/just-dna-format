"""Round-trip regression tests for the shapes the earlier 0.3/0.4 suite never exercised
(CONSTITUTION Principle 7 — lossless round-trip + idempotency). Each of these round-tripped
*wrongly* before the fix, while the happy path (rsid-keyed, uniform priority, no explicit-False
booleans) stayed green — so the invariant was only nominally "proven by tests".

Covered:
  * position-only variants keep their annotation (gene/phenotype/category) — keyed on variant_key,
    not the (null) rsid;
  * position-only study rows survive reverse → recompile instead of becoming identifier-less;
  * a partially-set `priority` is not fabricated for the rows that never set one;
  * an authored `pathogenic=false` / `benign=false` / `clinvar=false` is preserved (tri-state),
    not collapsed to None;
  * the artifact digest is a fixed point across compile → reverse → compile for all of the above.

All run with resolve_with_ensembl=False (no reference/network)."""

from pathlib import Path

import polars as pl
from just_dna_compiler.compiler import compile_module, reverse_module, validate_spec
from just_dna_format.spec import VariantRow

_YAML = """\
schema_version: "1.0"
module:
  name: demo_rt
  title: Round-trip Regressions
  description: fixture
  report_title: Report
genome_build: GRCh38
"""


def _write(d: Path, variants: str, studies: str) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "module_spec.yaml").write_text(_YAML, encoding="utf-8")
    (d / "variants.csv").write_text(variants, encoding="utf-8")
    (d / "studies.csv").write_text(studies, encoding="utf-8")
    return d


def _roundtrip(tmp_path: Path, variants: str, studies: str) -> tuple[Path, Path]:
    """compile → reverse → recompile; returns (orig_dir, recompiled_dir). Asserts the reversed spec
    re-validates and that the artifact digest is a fixed point."""
    spec = _write(tmp_path / "spec", variants, studies)
    orig = tmp_path / "orig"
    m1 = compile_module(spec, orig, resolve_with_ensembl=False)
    assert m1.success, m1.errors
    reverse_module(orig, tmp_path / "reversed")
    rev_validation = validate_spec(tmp_path / "reversed")
    assert rev_validation.valid, rev_validation.errors
    recompiled = tmp_path / "recompiled"
    m2 = compile_module(tmp_path / "reversed", recompiled, resolve_with_ensembl=False)
    assert m2.success, m2.errors
    assert m1.manifest.artifact.digest == m2.manifest.artifact.digest
    return orig, recompiled


def test_position_only_variant_keeps_annotation(tmp_path: Path) -> None:
    variants = (
        "chrom,start,ref,genotype,state,conclusion,gene,phenotype,category\n"
        "1,100,A,A/G,risk,c,BRCA1,breast cancer,cancer\n"
    )
    studies = "chrom,start,ref,pmid\n1,100,A,12345678\n"
    orig, recompiled = _roundtrip(tmp_path, variants, studies)

    ann = pl.read_parquet(recompiled / "annotations.parquet")
    row = ann.row(0, named=True)
    assert row["gene"] == "BRCA1"
    assert row["phenotype"] == "breast cancer"
    assert row["category"] == "cancer"
    # variant_key is materialized so the reverse lookup matches a null-rsid row.
    assert row["variant_key"] == "1:100:A"
    assert (
        pl.read_parquet(orig / "annotations.parquet")
        .equals(pl.read_parquet(recompiled / "annotations.parquet"))
    )


def test_position_only_study_survives_roundtrip(tmp_path: Path) -> None:
    variants = "chrom,start,ref,genotype,state,conclusion\n1,100,A,A/G,risk,c\n"
    studies = "chrom,start,ref,pmid,population\n1,100,A,12345678,EUR\n"
    orig, recompiled = _roundtrip(tmp_path, variants, studies)

    s = pl.read_parquet(recompiled / "studies.parquet").row(0, named=True)
    assert s["rsid"] is None
    assert (s["chrom"], s["start"], s["ref"]) == ("1", 100, "A")
    assert (
        pl.read_parquet(orig / "studies.parquet")
        .equals(pl.read_parquet(recompiled / "studies.parquet"))
    )


def test_partial_priority_is_not_fabricated(tmp_path: Path) -> None:
    # r1 sets priority=high, r2 leaves it unset and there is no defaults.priority: the unset row must
    # STAY unset across the round-trip, not inherit r1's value as an inferred default.
    variants = (
        "rsid,genotype,state,conclusion,priority\n"
        "rs1,A/G,risk,c,high\n"
        "rs2,A/G,risk,c,\n"
    )
    studies = "rsid,pmid\nrs1,12345678\nrs2,12345678\n"
    orig, recompiled = _roundtrip(tmp_path, variants, studies)

    def priorities(d: Path) -> list:
        w = pl.read_parquet(d / "weights.parquet").sort("rsid")
        return w["priority"].to_list()

    assert priorities(orig) == ["high", None]
    assert priorities(recompiled) == ["high", None]


def test_explicit_false_clinvar_booleans_survive(tmp_path: Path) -> None:
    # False is distinct from None ("stated not-pathogenic" vs "unstated"). It must round-trip.
    variants = (
        "rsid,genotype,state,conclusion,clinvar,pathogenic,benign\n"
        "rs1,A/G,risk,c,true,false,true\n"
    )
    studies = "rsid,pmid\nrs1,12345678\n"
    orig, recompiled = _roundtrip(tmp_path, variants, studies)

    for d in (orig, recompiled):
        w = pl.read_parquet(d / "weights.parquet").row(0, named=True)
        assert w["clinvar"] is True
        assert w["pathogenic"] is False   # NOT None
        assert w["benign"] is True

    # And the read-time alias stays False (the curator's explicit call), not derived-away.
    reversed_row = next(
        r for r in _read_csv(tmp_path / "reversed" / "variants.csv")
    )
    row = VariantRow.model_validate({k: v for k, v in reversed_row.items() if v != ""})
    assert row.pathogenic is False
    assert row.effective_pathogenic is False


def _read_csv(path: Path) -> list[dict]:
    import csv

    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))
