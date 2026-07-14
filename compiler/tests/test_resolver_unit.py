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
