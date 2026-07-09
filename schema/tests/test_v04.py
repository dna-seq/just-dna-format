"""0.4 schema-contract tests: the binning primitive, the PGx four-table model, and the PGS
declared interface. Compiler materialization is deferred (PROPOSAL_0_4), so these prove the
*authored contract* — validation, the mandatory `unresolved` outcome, the reserved-namespace
boundary, and model-level round-trip losslessness (Principle 7) — without touching the compiler.

Mirrors test_v03.py's inline-dict + `model_validate` style and its guard-the-vocabulary tests.
"""

import pytest
from pydantic import ValidationError

from just_dna_format.binning import (
    VALID_MEASURE_KINDS,
    ActivityPhenotypeRow,
    CopyNumberRow,
    HeteroplasmyRow,
    MeasureBinRow,
    RepeatAlleleRow,
    validate_bins,
)
from just_dna_format.pgs import (
    VALID_RESEARCH_TIERS,
    VALID_TRAINING_ANCESTRY,
    PgsRow,
)
from just_dna_format.pgx import (
    VALID_FUNCTION_STATUS,
    AlleleFunctionRow,
    DiplotypeRow,
    HaplotypeRow,
)
from just_dna_format.vocab import RESERVED_NAMES_0_4


# ── binning primitive ───────────────────────────────────────────────────────────────────────────
def test_repeat_allele_bins_accept_open_and_closed_ranges() -> None:
    # HTT CAG: open-ended (>=40), closed range (36-39), sharp handled elsewhere.
    full = RepeatAlleleRow(
        gene="HTT", repeat_unit="CAG", measure_min=40, direction="risk",
        clin_sig="pathogenic", phenotype="HD (full penetrance)",
        trait_efo_id="MONDO_0007739", conclusion=">=40 CAG",
    )
    assert full.measure_kind == "repeat_count"
    assert full.measure_max is None
    reduced = RepeatAlleleRow(
        gene="HTT", repeat_unit="CAG", measure_min=36, measure_max=39,
        direction="risk", clin_sig="pathogenic", conclusion="36-39 CAG",
    )
    assert (reduced.measure_min, reduced.measure_max) == (36.0, 39.0)


def test_copy_number_sharp_is_min_equals_max_and_modifier_pair() -> None:
    sharp = CopyNumberRow(
        gene="SMN1", measure_min=0, measure_max=0, modifier_gene="SMN2", modifier_cn=3,
        direction="risk", clin_sig="pathogenic", conclusion="0 SMN1 / 3 SMN2",
    )
    assert sharp.measure_min == sharp.measure_max == 0.0
    assert (sharp.modifier_gene, sharp.modifier_cn) == ("SMN2", 3)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"gene": "HTT", "repeat_unit": "CAG", "measure_min": 40, "measure_max": 30},  # min>max
        {"gene": "HTT", "repeat_unit": "CAG"},  # no bounds, not unresolved
        {"gene": "HTT", "repeat_unit": "CAG", "measure_min": 40, "caller": "advntr"},  # reserved
        {"gene": "HTT", "repeat_unit": "CAG", "measure_min": 40, "direction": "up"},  # bad direction
    ],
)
def test_repeat_allele_rejects_bad_rows(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        RepeatAlleleRow(conclusion="x", **kwargs)


def test_unresolved_sentinel_carries_no_bounds() -> None:
    ok = CopyNumberRow(gene="SMN1", unresolved=True, conclusion="not resolved; needs MLPA")
    assert ok.unresolved and ok.measure_min is None and ok.measure_max is None
    with pytest.raises(ValidationError):  # a sentinel must not carry a range
        CopyNumberRow(gene="SMN1", unresolved=True, measure_min=0, conclusion="x")


def test_copy_number_rejects_half_set_modifier() -> None:
    with pytest.raises(ValidationError):
        CopyNumberRow(gene="SMN1", measure_min=1, measure_max=1, modifier_gene="SMN2", conclusion="x")


def test_heteroplasmy_fraction_bounds_constrained_to_unit_interval() -> None:
    ok = HeteroplasmyRow(
        gene="MT-TL1", reference_sequence="NC_012920.1", measure_min=0.1, measure_max=0.6,
        direction="risk", conclusion="above penetrance threshold",
    )
    assert ok.measure_kind == "allele_fraction"
    with pytest.raises(ValidationError):
        HeteroplasmyRow(
            gene="MT-TL1", reference_sequence="NC_012920.1", measure_min=1.5, conclusion="x"
        )


def test_measure_kind_is_pinned_per_table() -> None:
    with pytest.raises(ValidationError):  # wrong kind for the subclass
        ActivityPhenotypeRow(gene="CYP2D6", measure_kind="copy_number", measure_min=1, conclusion="x")
    # base rejects an unknown kind entirely
    with pytest.raises(ValidationError):
        MeasureBinRow(measure_kind="bogus", measure_min=1, conclusion="x")


def test_measure_kinds_vocabulary_is_frozen() -> None:
    assert VALID_MEASURE_KINDS == frozenset(
        {"activity_score", "copy_number", "repeat_count", "allele_fraction", "prs_percentile"}
    )


# ── PGx four-table model ──────────────────────────────────────────────────────────────────────
def test_haplotype_junction_requires_identifier_and_nucleotide_allele() -> None:
    HaplotypeRow(haplotype_name="*4", rsid="rs3892097", allele="A", gene="CYP2D6")
    with pytest.raises(ValidationError):
        HaplotypeRow(haplotype_name="*4", allele="A")  # no rsid / position
    with pytest.raises(ValidationError):
        HaplotypeRow(haplotype_name="*4", rsid="rs1", allele="Z")  # not a nucleotide


def test_allele_function_star_string_verbatim_and_conveniences() -> None:
    dup = AlleleFunctionRow(
        gene="CYP2D6", allele="*1x2", activity_value=2.0,
        function_status="increased_function", copy_number=2,
    )
    assert dup.allele == "*1x2"
    tandem = AlleleFunctionRow(gene="CYP2D6", allele="*36+*10", activity_value=0.25, suballele="10.001")
    assert tandem.allele == "*36+*10" and tandem.suballele == "10.001"
    with pytest.raises(ValidationError):
        AlleleFunctionRow(gene="CYP2D6", allele="4")  # missing leading *
    with pytest.raises(ValidationError):
        AlleleFunctionRow(gene="CYP2D6", allele="*1", function_status="bogus")


def test_diplotype_pair_is_canonicalized() -> None:
    d = DiplotypeRow(gene="CYP2D6", haplotype_a="*4", haplotype_b="*1", phenotype="IM", conclusion="c")
    assert (d.haplotype_a, d.haplotype_b) == ("*1", "*4")  # swapped to lexicographic order
    same = DiplotypeRow(gene="CYP2D6", haplotype_a="*1", haplotype_b="*4", phenotype="IM", conclusion="c")
    assert (same.haplotype_a, same.haplotype_b) == ("*1", "*4")


def test_function_status_vocabulary_is_frozen() -> None:
    assert VALID_FUNCTION_STATUS == frozenset(
        {
            "no_function", "decreased_function", "normal_function",
            "increased_function", "uncertain_function", "unknown_function",
        }
    )


# ── PGS declared interface ────────────────────────────────────────────────────────────────────
def test_pgs_row_accepts_ancestry_validity_fields() -> None:
    p = PgsRow(
        pgs_id="PGS000135", trait_efo_id="EFO_0000692", training_ancestry="EUR|EAS",
        training_cohort="UK Biobank NW-EUR", match_rate_floor=0.8, research_tier="research_only",
        note="SCZ",
    )
    assert p.training_ancestry == ["EUR", "EAS"]
    assert p.training_cohort == "UK Biobank NW-EUR"
    assert p.match_rate_floor == 0.8 and p.research_tier == "research_only"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"pgs_id": "135"},  # not a PGS id
        {"pgs_id": "PGS1", "training_ancestry": "XXX"},  # unknown superpop
        {"pgs_id": "PGS1", "match_rate_floor": 1.2},  # out of [0,1]
        {"pgs_id": "PGS1", "research_tier": "clinical"},  # bad tier
        {"pgs_id": "PGS1", "match_rate": 0.9},  # renamed away → now an unknown field
        {"pgs_id": "PGS1", "caller": "prs"},  # reserved name
    ],
)
def test_pgs_row_rejects_bad_rows(kwargs: dict) -> None:
    with pytest.raises(ValidationError):
        PgsRow(**kwargs)


def test_pgs_vocabularies_are_frozen() -> None:
    assert VALID_TRAINING_ANCESTRY == frozenset({"EUR", "EAS", "AFR", "AMR", "SAS", "multi"})
    assert VALID_RESEARCH_TIERS == frozenset({"research_only", "calibrated"})


# ── reserved-namespace boundary + model-level round-trip (Principle 7) ──────────────────────────
def test_reserved_names_are_rejected_until_built() -> None:
    for name in RESERVED_NAMES_0_4:
        with pytest.raises(ValidationError):
            RepeatAlleleRow(
                gene="HTT", repeat_unit="CAG", measure_min=40, conclusion="x", **{name: "v"}
            )


def test_model_level_roundtrip_is_lossless_and_idempotent() -> None:
    rows = [
        RepeatAlleleRow(gene="HTT", repeat_unit="CAG", measure_min=36, measure_max=39,
                        direction="risk", clin_sig="pathogenic", conclusion="36-39"),
        CopyNumberRow(gene="SMN1", measure_min=0, measure_max=0, modifier_gene="SMN2",
                      modifier_cn=3, direction="risk", clin_sig="pathogenic", conclusion="0/3"),
        CopyNumberRow(gene="SMN1", unresolved=True, conclusion="not resolved"),
        HeteroplasmyRow(gene="MT-TL1", reference_sequence="NC_012920.1", measure_min=0.1,
                        measure_max=0.6, conclusion="threshold"),
        ActivityPhenotypeRow(gene="CYP2D6", measure_min=0, measure_max=0, phenotype="PM",
                             conclusion="poor metabolizer"),
        HaplotypeRow(haplotype_name="*4", rsid="rs3892097", allele="A", gene="CYP2D6"),
        AlleleFunctionRow(gene="CYP2D6", allele="*36+*10", activity_value=0.25, suballele="10.001"),
        DiplotypeRow(gene="CYP2D6", haplotype_a="*4", haplotype_b="*1", phenotype="IM", conclusion="c"),
        PgsRow(pgs_id="PGS000135", training_ancestry="EUR", match_rate_floor=0.8,
               research_tier="research_only"),
    ]
    for row in rows:
        reparsed = type(row).model_validate(row.model_dump())
        assert reparsed == row, f"round-trip changed {type(row).__name__}"
        # idempotent: a second pass is a fixpoint
        assert type(row).model_validate(reparsed.model_dump()) == reparsed


# ── round-2: source_field (VCF binding pointer, not code) ───────────────────────────────────────
def test_source_field_is_a_pointer_not_an_expression() -> None:
    assert RepeatAlleleRow(
        gene="HTT", repeat_unit="CAG", measure_min=40, conclusion=">=40", source_field="REPCN"
    ).source_field == "REPCN"
    assert CopyNumberRow(
        gene="SMN1", measure_min=0, measure_max=0, conclusion="0", source_field="CN|DS"
    ).source_field == "CN|DS"
    for bad in ("AF*DP", "AF + 1", "AF DP", "AF;DP"):
        with pytest.raises(ValidationError):
            RepeatAlleleRow(gene="HTT", repeat_unit="CAG", measure_min=40, conclusion="x", source_field=bad)


# ── round-2 Q6: heteroplasmy tissue + legacy reference guard ────────────────────────────────────
def test_heteroplasmy_tissue_fields_and_legacy_reference_guard() -> None:
    ok = HeteroplasmyRow(
        gene="MT-TL1", reference_sequence="NC_012920.1", measure_min=0.8, measure_max=1.0,
        conclusion="high", tissue="blood", assay_context="WGS",
    )
    assert ok.tissue == "blood" and ok.assay_context == "WGS"
    for legacy in ("NC_001807", "NC_001807.4"):
        with pytest.raises(ValidationError):  # confidently-wrong-haplogroup landmine
            HeteroplasmyRow(gene="MT-TL1", reference_sequence=legacy, measure_min=0.8, conclusion="x")


# ── round-2 C1: table-level bin coherence (overlap reject, gap warn, key-differentiated) ─────────
def _htt_bins() -> list[RepeatAlleleRow]:
    spans = [(6, 26, "normal"), (27, 35, "int"), (36, 39, "reduced"), (40, None, "full")]
    return [
        RepeatAlleleRow(gene="HTT", repeat_unit="CAG", measure_min=lo, measure_max=hi,
                        trait_efo_id="MONDO_0007739", conclusion=c)
        for lo, hi, c in spans
    ]


def test_validate_bins_accepts_contiguous_rejects_overlap_warns_gap() -> None:
    assert validate_bins(_htt_bins()) == []  # contiguous integer bins: no warning
    # drop the 36-39 bin → a real integer gap between 35 and 40
    gapped = [r for r in _htt_bins() if r.measure_min != 36]
    warns = validate_bins(gapped)
    assert warns and "no bin covers" in warns[0]
    # an overlapping resolved range is rejected outright
    overlap = _htt_bins() + [
        RepeatAlleleRow(gene="HTT", repeat_unit="CAG", measure_min=38, measure_max=45,
                        trait_efo_id="MONDO_0007739", conclusion="oops")
    ]
    with pytest.raises(ValueError):
        validate_bins(overlap)


def test_validate_bins_differentiates_by_modifier_and_trait() -> None:
    # two sharp [0,0] SMN1 rows differing only by SMN2 modifier are distinct keys, not an overlap
    smn = [
        CopyNumberRow(gene="SMN1", measure_min=0, measure_max=0, modifier_gene="SMN2", modifier_cn=3,
                      trait_efo_id="MONDO_0001516", conclusion="milder"),
        CopyNumberRow(gene="SMN1", measure_min=0, measure_max=0, modifier_gene="SMN2", modifier_cn=1,
                      trait_efo_id="MONDO_0001516", conclusion="severe"),
    ]
    assert validate_bins(smn) == []
    # unresolved sentinels are ignored (no range to overlap)
    assert validate_bins(_htt_bins() + [
        RepeatAlleleRow(gene="HTT", repeat_unit="CAG", unresolved=True,
                        trait_efo_id="MONDO_0007739", conclusion="CI")
    ]) == []
