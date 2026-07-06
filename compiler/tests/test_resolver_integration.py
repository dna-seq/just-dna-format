"""
Ensembl resolver integration tests against a real cache (SPEC §13 resolver regression).

These run only when an Ensembl cache is discoverable — i.e. `JUST_DNA_PIPELINES_CACHE_DIR` (the
same var just-dna-lite uses, typically set in `.env`) or `JUST_DNA_ENSEMBL_CACHE` points at one, or
the platformdirs default exists. They are **data-driven**: a real variant is sampled from whatever
cache is present, so they work with a full or partial cache and don't hardcode chromosomes.

`test_reference_resolves_from_env` verifies only the *mapping* (that the cache is located from the
environment) and runs whenever a cache dir exists — even if its data is empty/corrupt. The actual
resolution tests skip if the cache has no queryable rs-id rows.
"""

from pathlib import Path

import pytest

from just_dna_compiler.cache import resolve_ensembl_reference
from just_dna_compiler.resolver import _connect, resolve_variants
from just_dna_format.spec import VariantRow

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def reference() -> Path:
    ref = resolve_ensembl_reference()
    if ref is None:
        pytest.skip(
            "no Ensembl cache found — set JUST_DNA_PIPELINES_CACHE_DIR or JUST_DNA_ENSEMBL_CACHE"
        )
    return ref


@pytest.fixture(scope="module")
def sample_variant(reference: Path) -> dict:
    """A real (rsid, chrom, start, ref) sampled from the live cache, or skip if unusable."""
    try:
        con = _connect(reference)
        row = con.execute(
            "SELECT id, chrom, start, ref FROM ensembl_variations "
            "WHERE id LIKE 'rs%' AND ref IS NOT NULL LIMIT 1"
        ).fetchone()
        con.close()
    except Exception as exc:  # empty db + corrupt/absent parquet in a dev cache
        pytest.skip(f"Ensembl cache located but not queryable: {exc}")
    if not row:
        pytest.skip("Ensembl cache has no rs-id rows to sample")
    return {"rsid": row[0], "chrom": str(row[1]), "start": int(row[2]), "ref": str(row[3])}


def test_reference_resolves_from_env(reference: Path) -> None:
    """The cache is located purely from the environment (the .env mapping works)."""
    assert Path(reference).exists()


def test_rsid_resolves_to_position(reference: Path, sample_variant: dict) -> None:
    v = VariantRow(rsid=sample_variant["rsid"], genotype="A/G", weight=0.0,
                   state="neutral", conclusion="t")
    patched, _ = resolve_variants([v], reference)
    assert patched[0].chrom == sample_variant["chrom"]
    assert patched[0].start == sample_variant["start"]
    assert patched[0].ref == sample_variant["ref"]


def test_position_resolves_to_rsid(reference: Path, sample_variant: dict) -> None:
    v = VariantRow(chrom=sample_variant["chrom"], start=sample_variant["start"],
                   ref=sample_variant["ref"], genotype="A/G", weight=0.0,
                   state="neutral", conclusion="t")
    patched, _ = resolve_variants([v], reference)
    assert patched[0].rsid == sample_variant["rsid"]


def test_complete_variant_untouched(reference: Path, sample_variant: dict) -> None:
    v = VariantRow(rsid=sample_variant["rsid"], chrom=sample_variant["chrom"],
                   start=sample_variant["start"], ref=sample_variant["ref"], alts="A",
                   genotype="A/G", weight=0.0, state="risk", conclusion="complete")
    patched, warnings = resolve_variants([v], reference)
    assert patched[0].start == sample_variant["start"] and not warnings


def test_unknown_rsid_warns(reference: Path, sample_variant: dict) -> None:
    v = VariantRow(rsid="rs99999999999999", genotype="A/G", weight=0.0,
                   state="neutral", conclusion="t")
    patched, warnings = resolve_variants([v], reference)
    assert patched[0].chrom is None
    assert any("rs99999999999999" in w for w in warnings)
