"""Resolver unit tests over a **synthetic** in-memory Ensembl cache — no 190 MB reference and no
network, so unlike `test_resolver_integration.py` (integration-marked, skipped without a cache)
these run in normal CI. They cover the branches CI otherwise never touches: rsid ↔ position lookup,
the position-only-without-ref path (a key-format regression that silently never resolved), the
no-cache skip-with-warning fallback, and the unknown-rsid warning.

The resolver builds a view over `<cache>/data/*.parquet` (or `<cache>/*.parquet`), so a tiny
`ensembl_variations` parquet with the columns it queries (`id, chrom, start, ref, alt`) is a
complete, injectable reference."""

from pathlib import Path

import polars as pl
import pytest
from just_dna_compiler.resolver import resolve_variants
from just_dna_format.spec import VariantRow


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    data = tmp_path / "cache" / "data"
    data.mkdir(parents=True)
    pl.DataFrame(
        {
            "id": ["rs1801133", "rs429358", "rs7412"],
            "chrom": ["1", "19", "19"],
            "start": [11856377, 44908683, 44908821],
            "ref": ["G", "T", "C"],
            "alt": ["A", "C", "T"],
        }
    ).write_parquet(data / "chr.parquet")
    return tmp_path / "cache"


def _v(**kw) -> VariantRow:
    return VariantRow(genotype="A/G", state="neutral", conclusion="t", **kw)


def test_rsid_resolves_to_position(cache: Path) -> None:
    patched, warnings = resolve_variants([_v(rsid="rs1801133")], cache)
    assert (patched[0].chrom, patched[0].start, patched[0].ref) == ("1", 11856377, "G")
    assert not warnings


def test_position_with_ref_resolves_to_rsid(cache: Path) -> None:
    patched, _ = resolve_variants([_v(chrom="19", start=44908683, ref="T")], cache)
    assert patched[0].rsid == "rs429358"


def test_position_without_ref_resolves_to_rsid(cache: Path) -> None:
    # Regression: a ref-less position matched on (chrom, start) but the result was keyed by the DB
    # ref, so the caller's `chrom:start:None` lookup never hit and the variant stayed unresolved.
    patched, warnings = resolve_variants([_v(chrom="1", start=11856377)], cache)
    assert patched[0].rsid == "rs1801133"
    assert not any("no rsid found" in w for w in warnings)


def test_complete_variant_is_untouched(cache: Path) -> None:
    v = _v(rsid="rs1801133", chrom="1", start=11856377, ref="G")
    patched, warnings = resolve_variants([v], cache)
    assert patched[0] is v and not warnings


def test_unknown_rsid_warns_and_leaves_unset(cache: Path) -> None:
    patched, warnings = resolve_variants([_v(rsid="rs99999999")], cache)
    assert patched[0].chrom is None
    assert any("rs99999999" in w for w in warnings)


@pytest.fixture
def multiallelic_cache(tmp_path: Path) -> Path:
    # Two dbSNP ids share the SAME (chrom, start) but differ by ref — a multi-allelic site.
    data = tmp_path / "cache" / "data"
    data.mkdir(parents=True)
    pl.DataFrame(
        {
            "id": ["rs200", "rs100"],  # deliberately out of sorted order in the source
            "chrom": ["1", "1"],
            "start": [500, 500],
            "ref": ["G", "A"],
            "alt": ["T", "C"],
        }
    ).write_parquet(data / "chr.parquet")
    return tmp_path / "cache"


def test_refless_multiallelic_resolves_deterministically_and_warns(multiallelic_cache: Path) -> None:
    # A ref-less position over a multi-allelic site is genuinely ambiguous. Resolution must be
    # deterministic (ORDER BY chrom,start,ref,id picks the ref='A' row → rs100 regardless of source
    # row order or run) and must surface a warning rather than silently guessing.
    patched, warnings = resolve_variants([_v(chrom="1", start=500)], multiallelic_cache)
    assert patched[0].rsid == "rs100"
    assert any("multiple dbSNP ids" in w and "1:500" in w for w in warnings), warnings


def test_no_cache_skips_with_warning(tmp_path: Path) -> None:
    # An empty dir is not a usable reference: resolution is skipped (never a download), with a
    # warning, and the variants come back untouched.
    patched, warnings = resolve_variants([_v(rsid="rs1801133")], tmp_path / "empty")
    assert patched[0].chrom is None
    assert warnings and "skipped" in warnings[0]


# ── Identity freeze: resolution fills a member but never re-keys a row (Principle 7) ────────────


def test_one_to_one_rsid_keeps_rsid_key(cache: Path) -> None:
    # rs1801133 → exactly one locus: the coordinate is filled but the frozen variant_key stays the
    # rsid (the rsid uniquely identifies the row).
    patched, _ = resolve_variants([_v(rsid="rs1801133")], cache)
    assert len(patched) == 1
    assert patched[0].variant_key == "rs1801133"
    assert (patched[0].chrom, patched[0].start, patched[0].ref) == ("1", 11856377, "G")


def test_position_only_row_is_coord_keyed_after_resolution(cache: Path) -> None:
    # The P7 regression that motivated the work: a position-only row resolves to an rsid, but its
    # frozen key must STAY the coordinate — it must not flip to the resolved rsid.
    patched, _ = resolve_variants([_v(chrom="1", start=11856377, ref="G")], cache)
    assert patched[0].rsid == "rs1801133"       # rsid filled
    assert patched[0].variant_key == "1:11856377:G"  # key did NOT flip to the rsid


@pytest.fixture
def paralog_cache(tmp_path: Path) -> Path:
    # One rsid mapping to TWO distinct loci (a paralog/segmental-duplication shape).
    data = tmp_path / "cache" / "data"
    data.mkdir(parents=True)
    pl.DataFrame(
        {
            "id": ["rs555", "rs555"],
            "chrom": ["1", "16"],
            "start": [1000, 2000],
            "ref": ["A", "A"],
            "alt": ["G", "G"],
        }
    ).write_parquet(data / "chr.parquet")
    return tmp_path / "cache"


def test_one_to_many_rsid_expands_to_n_rows(paralog_cache: Path) -> None:
    # A no-coord rsid mapping to N>1 loci expands into N rows (a paralog/SV signal a consumer counts),
    # each keyed by its own coordinate, plus a warning.
    patched, warnings = resolve_variants([_v(rsid="rs555")], paralog_cache)
    assert len(patched) == 2
    assert {p.variant_key for p in patched} == {"1:1000:A", "16:2000:A"}
    assert all(p.rsid == "rs555" for p in patched)  # every row keeps the shared rsid as data
    assert any("maps to 2 loci" in w for w in warnings)


def test_expansion_order_is_deterministic(tmp_path: Path) -> None:
    # Source rows out of order → expansion still comes back sorted (ORDER BY id, chrom, start, ref),
    # so the compiled artifact is idempotent regardless of DB row order.
    data = tmp_path / "cache" / "data"
    data.mkdir(parents=True)
    pl.DataFrame(
        {
            "id": ["rs555", "rs555"],
            "chrom": ["16", "1"],       # deliberately reversed
            "start": [2000, 1000],
            "ref": ["A", "A"],
            "alt": ["G", "G"],
        }
    ).write_parquet(data / "chr.parquet")
    patched, _ = resolve_variants([_v(rsid="rs555")], tmp_path / "cache")
    assert [p.variant_key for p in patched] == ["1:1000:A", "16:2000:A"]


def test_both_identifiers_consistent_no_warning(cache: Path) -> None:
    # rsid + coord that agree with the reference → no consistency warning.
    _, warnings = resolve_variants([_v(rsid="rs1801133", chrom="1", start=11856377, ref="G")], cache)
    assert not any("disagreement" in w for w in warnings)


def test_both_identifiers_contradiction_warns(cache: Path) -> None:
    # rsid authored at a coordinate the reference maps elsewhere → a (non-fatal) warning.
    _, warnings = resolve_variants([_v(rsid="rs1801133", chrom="1", start=999, ref="T")], cache)
    assert any("disagreement" in w and "rs1801133" in w for w in warnings)


def test_consistency_skipped_when_reference_silent(cache: Path) -> None:
    # Neither the rsid nor the coordinate is in the reference → unverifiable → no warning.
    _, warnings = resolve_variants(
        [_v(rsid="rs00000001", chrom="7", start=42, ref="C")], cache
    )
    assert not any("disagreement" in w for w in warnings)


def test_non_grch38_build_skips_resolution(cache: Path) -> None:
    # The compiler is GRCh38-bound: a GRCh37 module is not resolved against the GRCh38 reference.
    patched, warnings = resolve_variants([_v(rsid="rs1801133")], cache, genome_build="GRCh37")
    assert patched[0].chrom is None
    assert any("GRCh38-bound" in w for w in warnings)
