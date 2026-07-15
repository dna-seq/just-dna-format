"""Compile-level round-trip tests for the frozen-identity fix (minimal B+, CONSTITUTION Principle 7),
driven through the resolver against a synthetic in-memory Ensembl cache (no network).

Covers the shapes the freeze exists for:
  * a position-only variant that resolves to an rsid reverses back to **position-only** (its key does
    not flip to the resolved rsid), and the round-trip digest is a fixed point;
  * a one-to-many rsid expands to N coord-keyed rows and reverses to N position-only rows, idempotent;
  * `weights.parquet` carries the frozen `variant_key`;
  * an old artifact lacking the `variant_key` column still reverses (fallback);
  * an orphan-study check matches on a shared coordinate, not frozen-key equality;
  * a malformed `provenance.json` is a compile error, not an uncaught exception.
"""

import csv
from pathlib import Path

import polars as pl
import pytest
from just_dna_compiler.compiler import compile_module, reverse_module, validate_spec

_YAML = """\
schema_version: "1.0"
module:
  name: demo_id
  title: Identity Round-trip
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


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    data = tmp_path / "cache" / "data"
    data.mkdir(parents=True)
    pl.DataFrame(
        {
            "id": ["rs1801133", "rs555", "rs555"],
            "chrom": ["1", "1", "16"],
            "start": [11856377, 1000, 2000],
            "ref": ["G", "A", "A"],
            "alt": ["A", "G", "G"],
        }
    ).write_parquet(data / "chr.parquet")
    return tmp_path / "cache"


def test_position_only_resolves_but_reverses_position_only(tmp_path: Path, cache: Path) -> None:
    spec = _write(
        tmp_path / "spec",
        "chrom,start,ref,genotype,state,conclusion\n1,11856377,G,A/G,risk,c\n",
        "chrom,start,ref,pmid\n1,11856377,G,12345678\n",
    )
    m1 = compile_module(spec, tmp_path / "o1", ensembl_cache=cache)
    assert m1.success, m1.errors

    w = pl.read_parquet(tmp_path / "o1" / "weights.parquet").row(0, named=True)
    assert w["rsid"] == "rs1801133"          # rsid was resolved
    assert w["variant_key"] == "1:11856377:G"  # key did NOT flip to the rsid

    reverse_module(tmp_path / "o1", tmp_path / "rev")
    row = _read_csv(tmp_path / "rev" / "variants.csv")[0]
    assert row["rsid"] == ""                 # resolved rsid dropped → authored (position-only) shape
    assert (row["chrom"], row["start"], row["ref"]) == ("1", "11856377", "G")

    assert validate_spec(tmp_path / "rev").valid
    m2 = compile_module(tmp_path / "rev", tmp_path / "o2", ensembl_cache=cache)
    assert m2.success, m2.errors
    assert m1.manifest.artifact.digest == m2.manifest.artifact.digest  # fixed point


def test_expanded_rsid_roundtrips_as_position_only(tmp_path: Path, cache: Path) -> None:
    spec = _write(
        tmp_path / "spec",
        "rsid,genotype,state,conclusion\nrs555,A/G,risk,c\n",
        "rsid,pmid\nrs555,12345678\n",
    )
    m1 = compile_module(spec, tmp_path / "o1", ensembl_cache=cache)
    assert m1.success, m1.errors

    w = pl.read_parquet(tmp_path / "o1" / "weights.parquet")
    assert w.height == 2  # one row per paralogous locus
    assert set(w["variant_key"].to_list()) == {"1:1000:A", "16:2000:A"}
    assert set(w["rsid"].to_list()) == {"rs555"}  # rsid kept as data on every row

    reverse_module(tmp_path / "o1", tmp_path / "rev")
    rows = _read_csv(tmp_path / "rev" / "variants.csv")
    assert len(rows) == 2
    assert all(r["rsid"] == "" for r in rows)  # coord-keyed → position-only

    m2 = compile_module(tmp_path / "rev", tmp_path / "o2", ensembl_cache=cache)
    assert m2.success, m2.errors
    assert m1.manifest.artifact.digest == m2.manifest.artifact.digest


def test_old_artifact_without_variant_key_column_reverses(tmp_path: Path) -> None:
    # An artifact compiled before the frozen-key column existed: reverse must fall back to the derived
    # key and still produce a valid spec.
    spec = _write(
        tmp_path / "spec",
        "rsid,genotype,state,conclusion,gene\nrs1,A/G,risk,c,MTHFR\n",
        "rsid,pmid\nrs1,12345678\n",
    )
    out = tmp_path / "o"
    assert compile_module(spec, out, resolve_with_ensembl=False).success
    # Simulate an old artifact: drop the variant_key column from weights.parquet.
    w = pl.read_parquet(out / "weights.parquet").drop("variant_key")
    w.write_parquet(out / "weights.parquet")

    reverse_module(out, tmp_path / "rev")
    row = _read_csv(tmp_path / "rev" / "variants.csv")[0]
    assert row["rsid"] == "rs1"
    assert row["gene"] == "MTHFR"
    assert validate_spec(tmp_path / "rev").valid


def test_orphan_study_matches_on_shared_coord(tmp_path: Path) -> None:
    # A position-only variant grounded by a study that references the same coordinate must NOT be
    # flagged as an orphan (match on shared identifier, not frozen-key equality).
    spec = _write(
        tmp_path / "spec",
        "chrom,start,ref,genotype,state,conclusion\n1,100,A,A/G,risk,c\n",
        "chrom,start,ref,pmid\n1,100,A,12345678\n",
    )
    result = validate_spec(spec)
    assert result.valid, result.errors
    assert not any("reference variants not in" in w for w in result.warnings)


def test_mixed_authoring_no_false_inconsistency(tmp_path: Path) -> None:
    # Same rsid on two genotype rows, one carrying coords and one not: the position-consistency check
    # must not treat the absent position as a conflicting one (it compares only positioned rows).
    spec = _write(
        tmp_path / "spec",
        "rsid,chrom,start,ref,genotype,state,conclusion\n"
        "rs1,1,100,A,A/G,risk,c\n"
        "rs1,,,,A/A,risk,c\n",
        "rsid,pmid\nrs1,12345678\n",
    )
    result = validate_spec(spec)
    assert result.valid, result.errors
    assert not any("Inconsistent positions" in e for e in result.errors)


def test_malformed_provenance_returns_compile_error(tmp_path: Path) -> None:
    spec = _write(
        tmp_path / "spec",
        "rsid,genotype,state,conclusion\nrs1,A/G,risk,c\n",
        "rsid,pmid\nrs1,12345678\n",
    )
    (spec / "provenance.json").write_text('{"items": [{"bogus": true}]}', encoding="utf-8")
    result = compile_module(spec, tmp_path / "o", resolve_with_ensembl=False)
    assert not result.success
    assert any("provenance.json is invalid" in e for e in result.errors)
