"""0.3 additive schema + compiler coverage: the new optional columns (direction, stat_significance,
effect_size/measure, effect_allele, flags, trait_efo_id, clin_sig), the widened genotype validator
(hemizygous single-allele + phased), and the compiler-side validation extras (flags INFO, MT and
direction/weight warnings). Materialization of the new columns is exercised end-to-end.

Only the *validator* is complete in 0.3; computed derivations are intentionally deferred — see
docs/COMPILER.md. These tests target what IS implemented, and assert the deferrals where relevant.

All run with resolve_with_ensembl=False (no reference/network needed)."""

from pathlib import Path

import polars as pl
import pytest
from just_dna_format.spec import (
    RESERVED_FLAGS,
    VALID_CLIN_SIG,
    VALID_DIRECTIONS,
    VALID_SIGNIFICANCE,
    StudyRow,
    VariantRow,
)
from pydantic import ValidationError

from just_dna_compiler.compiler import compile_module, validate_spec

_YAML = """\
schema_version: "1.0"
module:
  name: demo3
  title: Demo Three
  description: A 0.3 demo module
  report_title: Demo Three Report
  color: "#21ba45"
defaults:
  curator: tester
  method: manual
genome_build: GRCh38
"""

# Two rows exercising every new VariantRow column, plus a non-reserved flag ("curated").
_VARIANTS = """\
rsid,genotype,weight,state,conclusion,direction,stat_significance,effect_size,effect_measure,effect_allele,flags,trait_efo_id,clin_sig
rs1801133,A/G,0.5,protective,ok,protective,significant,0.6,OR,A,conditional|curated,EFO_0004518,likely_benign
rs429358,C/T,-0.3,risk,bad,risk,suggestive,3.2,OR,C,pleiotropic,MONDO:0005265,pathogenic
"""

_STUDIES = """\
rsid,pmid,population,p_value,conclusion,study_design,stat_significance,effect_size,effect_measure,trait_efo_id
rs1801133,12345,EUR,0.01,assoc,GWAS,significant,0.6,OR,EFO_0004518
rs429358,67890,EUR,0.001,assoc,meta-analysis,suggestive,3.2,OR,MONDO:0005265
"""


def _write_spec(d: Path, variants: str = _VARIANTS, studies: str = _STUDIES) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    (d / "module_spec.yaml").write_text(_YAML, encoding="utf-8")
    (d / "variants.csv").write_text(variants, encoding="utf-8")
    (d / "studies.csv").write_text(studies, encoding="utf-8")
    return d


def _variant(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "rsid": "rs1801133",
        "genotype": "A/G",
        "state": "risk",
        "conclusion": "x",
    }
    base.update(overrides)
    return base


# ── Validator: new column vocabularies (complete) ───────────────────────────────


def test_valid_new_columns_accepted() -> None:
    row = VariantRow.model_validate(
        _variant(
            direction="protective",
            stat_significance="suggestive",
            effect_size=1.5,
            effect_measure="beta",
            effect_allele="A",
            trait_efo_id="EFO_0004518",
            clin_sig="likely_pathogenic",
        )
    )
    assert row.direction == "protective"
    assert row.effect_size == 1.5
    assert row.clin_sig == "likely_pathogenic"


@pytest.mark.parametrize(
    "field,bad",
    [
        ("direction", "damaging"),  # not in VALID_DIRECTIONS
        ("stat_significance", "very"),  # not in VALID_SIGNIFICANCE
        ("clin_sig", "totally_pathogenic"),  # not in VALID_CLIN_SIG
        ("effect_allele", "X"),  # not a nucleotide
        ("trait_efo_id", "coronary artery disease"),  # not a CURIE
    ],
)
def test_invalid_vocab_rejected(field: str, bad: str) -> None:
    with pytest.raises(ValidationError):
        VariantRow.model_validate(_variant(**{field: bad}))


def test_vocab_constants_are_the_contract() -> None:
    # Guard the enum sets so a silent vocab change is caught.
    assert VALID_DIRECTIONS == {"protective", "risk", "neutral", "unknown"}
    assert VALID_SIGNIFICANCE == {"significant", "suggestive", "not_significant", "unknown"}
    assert {"pathogenic", "likely_pathogenic", "uncertain_significance", "benign"} <= VALID_CLIN_SIG
    assert RESERVED_FLAGS == {"conditional", "phased", "pleiotropic"}


def test_effect_measure_is_permissive() -> None:
    # effect_measure is intentionally NOT a closed vocabulary (PGS weight_type may add values).
    assert VariantRow.model_validate(_variant(effect_measure="some_new_unit")).effect_measure == (
        "some_new_unit"
    )


# ── Validator: genotype widening (hemizygous + phased) ──────────────────────────


@pytest.mark.parametrize("gt", ["A", "A/G", "A|G", "G|A", "AC/AT", "T"])
def test_genotype_forms_accepted(gt: str) -> None:
    assert VariantRow.model_validate(_variant(genotype=gt)).genotype == gt


@pytest.mark.parametrize("gt", ["G/A", "A|G|C", "A/G/T", "A|X", "Z", "/"])
def test_genotype_forms_rejected(gt: str) -> None:
    # unsorted unphased, >2 alleles, non-nucleotide, empty.
    with pytest.raises(ValidationError):
        VariantRow.model_validate(_variant(genotype=gt))


def test_phased_genotype_not_sorted() -> None:
    # Phase is order-significant, so a "reverse-sorted" phased pair must be accepted as-is.
    assert VariantRow.model_validate(_variant(genotype="T|C")).genotype == "T|C"


# ── Validator: flags open vocabulary + splitting ────────────────────────────────


def test_flags_split_from_csv_cell() -> None:
    row = VariantRow.model_validate(_variant(flags="conditional|curated;phased"))
    assert row.flags == ["conditional", "curated", "phased"]


def test_flags_unknown_tags_surface_as_info_not_warning(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path)
    result = validate_spec(spec)
    assert result.valid
    # The non-reserved tag "curated" is reported as the unknown-tag list; the reserved "conditional"
    # is not (it may appear in the note's "reserved tags are [...]" context, so match the list).
    assert any("['curated']" in note for note in result.info)
    assert not any("curated" in w for w in result.warnings)


# ── Validator: cross-row warnings ───────────────────────────────────────────────


def test_mt_two_allele_genotype_warns(tmp_path: Path) -> None:
    variants = (
        "chrom,start,ref,alts,genotype,state,conclusion\n"
        "MT,3243,A,G,A/G,risk,MELAS diploid-looking (wrong)\n"
    )
    spec = _write_spec(
        tmp_path, variants=variants, studies="chrom,start,ref,pmid\nMT,3243,A,12345\n"
    )
    result = validate_spec(spec)
    assert any("MT is not diploid" in w for w in result.warnings)


def test_mt_single_allele_genotype_ok(tmp_path: Path) -> None:
    variants = (
        "chrom,start,ref,alts,genotype,state,conclusion\n"
        "MT,3243,A,G,G,risk,homoplasmic m.3243A>G\n"
    )
    spec = _write_spec(
        tmp_path, variants=variants, studies="chrom,start,ref,pmid\nMT,3243,A,12345\n"
    )
    result = validate_spec(spec)
    assert result.valid
    assert not any("MT is not diploid" in w for w in result.warnings)


def test_direction_weight_inconsistency_warns(tmp_path: Path) -> None:
    variants = (
        "rsid,genotype,weight,state,conclusion,direction\n"
        "rs1801133,A/G,0.9,neutral,ok,risk\n"  # direction=risk but weight>0
    )
    spec = _write_spec(tmp_path, variants=variants)
    result = validate_spec(spec)
    assert any("direction='risk' but weight" in w for w in result.warnings)


# ── Materialization (passthrough) into weights.parquet ──────────────────────────


def test_new_columns_materialize_into_weights(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path / "spec")
    out = tmp_path / "out"
    result = compile_module(spec, out, resolve_with_ensembl=False)
    assert result.success, result.errors

    weights = pl.read_parquet(out / "weights.parquet")
    for col in (
        "direction",
        "stat_significance",
        "effect_size",
        "effect_measure",
        "effect_allele",
        "flags",
        "trait_efo_id",
        "clin_sig",
    ):
        assert col in weights.columns

    protective = weights.filter(pl.col("rsid") == "rs1801133").row(0, named=True)
    assert protective["direction"] == "protective"
    assert protective["stat_significance"] == "significant"
    assert protective["effect_size"] == pytest.approx(0.6)
    assert protective["effect_allele"] == "A"
    assert protective["clin_sig"] == "likely_benign"
    assert set(protective["flags"]) == {"conditional", "curated"}
    assert protective["trait_efo_id"] == "EFO_0004518"


def test_study_new_columns_materialize(tmp_path: Path) -> None:
    spec = _write_spec(tmp_path / "spec")
    out = tmp_path / "out"
    assert compile_module(spec, out, resolve_with_ensembl=False).success
    studies = pl.read_parquet(out / "studies.parquet")
    for col in ("stat_significance", "effect_size", "effect_measure", "trait_efo_id"):
        assert col in studies.columns
    row = studies.filter(pl.col("rsid") == "rs429358").row(0, named=True)
    assert row["stat_significance"] == "suggestive"
    assert row["effect_size"] == pytest.approx(3.2)
    assert row["trait_efo_id"] == "MONDO:0005265"


def test_hemizygous_and_single_allele_survive_compile(tmp_path: Path) -> None:
    variants = (
        "rsid,genotype,state,conclusion\n"
        "rs1050828,T,risk,hemizygous deficient\n"
    )
    spec = _write_spec(tmp_path / "spec", variants=variants)
    out = tmp_path / "out"
    assert compile_module(spec, out, resolve_with_ensembl=False).success
    weights = pl.read_parquet(out / "weights.parquet")
    assert weights.row(0, named=True)["genotype"] == ["T"]


# ── StudyRow validation of the new columns ──────────────────────────────────────


def test_study_row_vocab_validation() -> None:
    assert StudyRow.model_validate(
        {"rsid": "rs1", "pmid": "123", "stat_significance": "not_significant"}
    ).stat_significance == "not_significant"
    with pytest.raises(ValidationError):
        StudyRow.model_validate({"rsid": "rs1", "pmid": "123", "stat_significance": "maybe"})
    with pytest.raises(ValidationError):
        StudyRow.model_validate({"rsid": "rs1", "pmid": "123", "trait_efo_id": "not a curie!"})
