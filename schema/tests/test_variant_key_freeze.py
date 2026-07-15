"""The frozen `variant_key` (minimal-B+ identity fix). `VariantRow.variant_key` is a stored column
stamped once at load and never re-derived, so the resolver filling a coord/rsid — or expanding a
one-to-many rsid — can never re-key a row (CONSTITUTION Principle 7). It is compiler-managed: not
part of the authored DSL surface, never written back by `reverse_module`."""

from just_dna_format.base import derive_variant_key
from just_dna_format.reference import authoring_reference
from just_dna_format.spec import VariantRow


def _v(**kw) -> VariantRow:
    return VariantRow(genotype="A/G", state="neutral", conclusion="c", **kw)


def test_variant_key_backfilled_at_load() -> None:
    assert _v(rsid="rs1").variant_key == "rs1"                     # rsid uniquely identifies
    assert _v(chrom="1", start=100, ref="A").variant_key == "1:100:A"  # position-only → coord
    assert _v(rsid="rs1", chrom="1", start=100, ref="A").variant_key == "rs1"  # rsid wins


def test_variant_key_frozen_survives_model_copy() -> None:
    # A position-only row that later gets an rsid filled (as the resolver does) keeps its coord key:
    # model_copy does not re-run the after-validator, so the frozen identity does not flip.
    row = _v(chrom="1", start=100, ref="A")
    assert row.variant_key == "1:100:A"
    resolved = row.model_copy(update={"rsid": "rs1"})
    assert resolved.rsid == "rs1"
    assert resolved.variant_key == "1:100:A"  # NOT "rs1"


def test_authored_variant_key_is_ignored() -> None:
    # A human cannot inject an arbitrary key: the backfill validator derives it unconditionally.
    row = _v(rsid="rs1", variant_key="not-a-real-key")
    assert row.variant_key == "rs1"


def test_variant_key_absent_from_authoring_reference() -> None:
    # The machine field must not read as an authored field in the human-facing reference (RM8).
    fields = {f["name"] for f in authoring_reference()["models"]["VariantRow"]}
    assert "variant_key" not in fields
    assert "rsid" in fields and "genotype" in fields  # sanity: real fields still present


def test_reversed_csv_shape_without_variant_key_validates() -> None:
    # reverse_module never writes a variant_key column; a row lacking it must still validate
    # (the field defaults to None, then the validator stamps it) — extra="forbid" is unaffected.
    row = VariantRow.model_validate(
        {"rsid": "rs1", "genotype": "A/G", "state": "neutral", "conclusion": "c"}
    )
    assert row.variant_key == "rs1"


def test_derive_variant_key_helper() -> None:
    assert derive_variant_key("rs9", "1", 5, "A") == "rs9"
    assert derive_variant_key(None, "1", 5, "A") == "1:5:A"
