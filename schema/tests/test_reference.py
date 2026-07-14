"""RM8/RM9 — the drift-proof authoring reference and the recommended display palette."""

import json

import pytest

from just_dna_format.binning import VALID_MEASURE_KINDS
from just_dna_format.manifest import COLOR_PATTERN, RECOMMENDED_COLORS, RECOMMENDED_ICONS
from just_dna_format.reference import authoring_reference, json_schemas


def test_authoring_reference_is_json_serializable_with_expected_shape() -> None:
    ref = authoring_reference()
    json.dumps(ref)  # a single source of truth must serialise for MCP/agents/docs
    assert set(ref) >= {
        "schema_version", "genome_build_default", "models", "vocabularies",
        "reserved_names", "recommended_palette",
    }
    assert ref["genome_build_default"] == "GRCh38"


def test_authoring_reference_is_generated_not_hardcoded() -> None:
    # Drift-proofing: fields/vocab come from the live models, so they include the 0.3/0.4 additions.
    ref = authoring_reference()
    variant_fields = {f["name"] for f in ref["models"]["VariantRow"]}
    assert {"direction", "clin_sig", "effect_allele", "trait_efo_id"} <= variant_fields
    cn_fields = {f["name"] for f in ref["models"]["CopyNumberRow"]}
    assert {"modifier_gene", "modifier_cn", "source_field", "unresolved"} <= cn_fields
    assert {"tissue", "reference_sequence"} <= {f["name"] for f in ref["models"]["HeteroplasmyRow"]}
    assert {"match_rate_floor", "training_cohort"} <= {f["name"] for f in ref["models"]["PgsRow"]}
    # the vocab is the live frozenset, not a copy that could drift
    assert ref["vocabularies"]["measure_kind"] == sorted(VALID_MEASURE_KINDS)
    assert "callable_from" in ref["reserved_names"]
    assert "descriptive" in ref["open_recommended"]["actionability_seed"]
    # adoption pass: PharmVariantRow + evidence_level + the VariantRow axes appear (generated)
    assert "PharmVariantRow" in ref["models"]
    assert ref["vocabularies"]["evidence_level"] == ["1A", "1B", "2A", "2B", "3", "4"]
    assert {"requires_callable", "acmg_sf", "actionability"} <= {
        f["name"] for f in ref["models"]["VariantRow"]
    }
    # retired names are no longer reserved (they became VariantRow columns)
    assert not ({"requires_callable", "acmg_sf", "actionability"} & set(ref["reserved_names"]))
    # RM14 authorship: the Contribution model + role vocab + open kind seed all surface (generated)
    assert {"who", "role", "kind", "at"} == {f["name"] for f in ref["models"]["Contribution"]}
    assert ref["vocabularies"]["author_role"] == ["audited", "created", "edited", "reviewed"]
    assert {"human", "human_expert", "human_certified", "ai", "swarm"} <= set(
        ref["open_recommended"]["author_kind"]
    )


def test_authoring_reference_field_records_carry_type_required_description() -> None:
    genotype = next(
        f for f in authoring_reference()["models"]["VariantRow"] if f["name"] == "genotype"
    )
    assert genotype["required"] is True
    assert genotype["type"] == "str"
    assert genotype["description"]  # non-empty


def test_recommended_palette_is_valid() -> None:
    assert RECOMMENDED_COLORS and RECOMMENDED_ICONS
    for use, hex_code in RECOMMENDED_COLORS.items():
        assert COLOR_PATTERN.match(hex_code), f"{use} → {hex_code} not a 6-hex colour"
    for use, glyph in RECOMMENDED_ICONS.items():
        assert glyph and isinstance(glyph, str)
    # the palette is surfaced through the reference too
    assert authoring_reference()["recommended_palette"]["colors"] == RECOMMENDED_COLORS


def test_json_schemas_returns_a_schema_per_model() -> None:
    schemas = json_schemas()
    assert "VariantRow" in schemas and "properties" in schemas["VariantRow"]
    assert "CopyNumberRow" in schemas and "PgsRow" in schemas
    json.dumps(schemas)  # serialisable
