"""DSL spec model tests — validation mirrors the authored module_spec.yaml / CSV rules."""

import pytest
from pydantic import ValidationError

from just_dna_format.spec import ModuleInfo, ModuleSpecConfig, StudyRow, VariantRow


def test_module_info_reuses_name_and_color_rules() -> None:
    ModuleInfo(name="coronary", title="T", description="d", report_title="R", color="#21ba45")
    with pytest.raises(ValidationError):
        ModuleInfo(name="Bad Name", title="T", description="d", report_title="R")
    with pytest.raises(ValidationError):
        ModuleInfo(name="ok", title="T", description="d", report_title="R", color="red")


def test_variant_requires_an_identifier() -> None:
    with pytest.raises(ValidationError):
        VariantRow(genotype="A/G", state="risk", conclusion="c")  # no rsid, no position


def test_variant_key_and_genotype_rules() -> None:
    v = VariantRow(rsid="rs1801133", genotype="A/G", state="risk", conclusion="c")
    assert v.variant_key == "rs1801133"
    with pytest.raises(ValidationError):
        VariantRow(rsid="rs1", genotype="G/A", state="risk", conclusion="c")  # not sorted
    with pytest.raises(ValidationError):
        VariantRow(rsid="bad", genotype="A/G", state="risk", conclusion="c")  # rsid pattern


def test_spec_config_rejects_unknown_schema_version() -> None:
    module = {"name": "m", "title": "T", "description": "d", "report_title": "R"}
    ModuleSpecConfig(module=module)  # default schema_version ok
    with pytest.raises(ValidationError):
        ModuleSpecConfig(schema_version="9.9", module=module)


def test_study_requires_pmid_and_identifier() -> None:
    StudyRow(rsid="rs1", pmid="12345")
    with pytest.raises(ValidationError):
        StudyRow(pmid="")  # empty pmid and no identifier


def test_start_position_must_be_non_negative() -> None:
    # start is materialized as an unsigned parquet column; a negative position is a clean
    # validation error rather than a downstream polars overflow.
    VariantRow(chrom="1", start=0, genotype="A/G", state="risk", conclusion="c")
    with pytest.raises(ValidationError):
        VariantRow(chrom="1", start=-1, genotype="A/G", state="risk", conclusion="c")
    with pytest.raises(ValidationError):
        StudyRow(chrom="1", start=-1, pmid="12345")


def test_non_finite_floats_rejected() -> None:
    # NaN/inf break round-trip equality (needs_upgrade oscillation) and serialize to non-reloadable
    # cells; an authored numeric field is always finite.
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValidationError):
            VariantRow(rsid="rs1", genotype="A/G", state="risk", conclusion="c", weight=bad)
        with pytest.raises(ValidationError):
            VariantRow(rsid="rs1", genotype="A/G", state="risk", conclusion="c", effect_size=bad)
        with pytest.raises(ValidationError):
            StudyRow(rsid="rs1", pmid="12345", effect_size=bad)
