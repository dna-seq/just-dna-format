"""
DSL model regression tests ported from just-dna-lite's `test_module_compiler.py` (the model
unit-test half), repointed to `just_dna_format.spec`. Preserved here because the compiler code —
and these tests — are being removed from just-dna-lite.
"""

import pytest

from just_dna_format.spec import ModuleInfo, ModuleSpecConfig, StudyRow, VariantRow


class TestModuleSpecConfig:
    def test_invalid_module_name(self) -> None:
        with pytest.raises(Exception):
            ModuleInfo(name="Bad Name!", title="T", description="D", report_title="R")

    def test_invalid_schema_version(self) -> None:
        with pytest.raises(Exception):
            ModuleSpecConfig(
                schema_version="2.0",
                module=ModuleInfo(name="test", title="T", description="D", report_title="R"),
            )

    def test_defaults_applied(self) -> None:
        config = ModuleSpecConfig(
            module=ModuleInfo(name="test", title="T", description="D", report_title="R")
        )
        assert config.schema_version == "1.0"
        assert config.genome_build == "GRCh38"
        assert config.defaults.curator == "ai-module-creator"


class TestVariantRow:
    def test_valid_row_with_both(self) -> None:
        row = VariantRow(
            rsid="rs1801133", chrom="1", start=11796321, ref="G", alts="A",
            genotype="A/G", weight=-0.5, state="risk", conclusion="Heterozygous",
            gene="MTHFR", phenotype="Reduced methylation", category="methylation",
        )
        assert row.variant_key == "rs1801133"

    def test_position_only_valid(self) -> None:
        row = VariantRow(
            chrom="10", start=94781859, ref="G", alts="A", genotype="A/G",
            weight=-0.5, state="risk", conclusion="Position-only",
        )
        assert row.rsid is None
        assert row.variant_key == "10:94781859:G"

    def test_neither_rsid_nor_position_rejected(self) -> None:
        with pytest.raises(Exception, match="At least one identifier"):
            VariantRow(genotype="A/G", weight=0.0, state="neutral", conclusion="Test")

    def test_invalid_rsid(self) -> None:
        with pytest.raises(Exception, match="rsid"):
            VariantRow(rsid="notAnRsid", genotype="A/G", weight=0.0, state="neutral", conclusion="T")

    def test_unsorted_genotype_rejected(self) -> None:
        with pytest.raises(Exception, match="alphabetically sorted"):
            VariantRow(rsid="rs123", genotype="G/A", weight=0.0, state="neutral", conclusion="T")

    def test_invalid_state(self) -> None:
        with pytest.raises(Exception, match="state"):
            VariantRow(rsid="rs123", genotype="A/G", weight=0.0, state="bad_state", conclusion="T")

    def test_chrom_normalization(self) -> None:
        row = VariantRow(
            rsid="rs123", chrom="chr1", start=100, genotype="A/G",
            weight=0.0, state="neutral", conclusion="Test",
        )
        assert row.chrom == "1"

    def test_partial_position_rejected(self) -> None:
        with pytest.raises(Exception, match="chrom and start are required"):
            VariantRow(
                rsid="rs123", chrom="1", start=None, genotype="A/G",
                weight=0.0, state="neutral", conclusion="Test",
            )

    def test_ref_without_position_rejected(self) -> None:
        with pytest.raises(Exception, match="ref/alts require chrom and start"):
            VariantRow(
                rsid="rs123", ref="A", genotype="A/G", weight=0.0,
                state="neutral", conclusion="Test",
            )


class TestStudyRow:
    def test_valid_study_with_rsid(self) -> None:
        assert StudyRow(rsid="rs1801133", pmid="9545397", conclusion="Test").variant_key == "rs1801133"

    def test_valid_study_with_position(self) -> None:
        row = StudyRow(chrom="10", start=94781859, ref="G", pmid="12345", conclusion="Test")
        assert row.variant_key == "10:94781859:G"

    def test_study_no_id_rejected(self) -> None:
        with pytest.raises(Exception, match="At least one identifier"):
            StudyRow(pmid="12345", conclusion="Test")

    def test_empty_pmid_rejected(self) -> None:
        with pytest.raises(Exception, match="pmid"):
            StudyRow(rsid="rs123", pmid="", conclusion="Test")

    def test_freeform_pmid_accepted(self) -> None:
        row = StudyRow(rsid="rs123", pmid="PMID 17478681; PMID 21378990;", conclusion="Test")
        assert row.pmid == "PMID 17478681; PMID 21378990;"
