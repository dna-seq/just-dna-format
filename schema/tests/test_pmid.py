"""PMID validation (ROADMAP item 6): accept the Gen-I forms, keep the string verbatim, reject
non-PMID references like dbSNP URLs."""

import pytest
from just_dna_format.spec import StudyRow, extract_pmids


def test_extract_bare_bracketed_and_listed() -> None:
    assert extract_pmids("9545397") == ["9545397"]
    assert extract_pmids("[PMID: 9545397]") == ["9545397"]
    assert extract_pmids("PMID 17478681; PMID: 30278588") == ["17478681", "30278588"]
    # A PubMed URL carries the PMID at a word boundary → extractable.
    assert extract_pmids("https://pubmed.ncbi.nlm.nih.gov/29165669/") == ["29165669"]


def test_extract_dedups_preserving_order() -> None:
    assert extract_pmids("PMID 123; PMID 123; PMID 456") == ["123", "456"]


def test_studyrow_accepts_legacy_bracketed_and_keeps_verbatim() -> None:
    s = StudyRow(rsid="rs1", pmid="PMID 17478681; PMID 21378990;")
    assert s.pmid == "PMID 17478681; PMID 21378990;"  # unchanged
    assert extract_pmids(s.pmid) == ["17478681", "21378990"]


def test_studyrow_rejects_dbsnp_url() -> None:
    # A dbSNP URL has no PMID token (the digits are embedded in `rs...`, not at a boundary).
    with pytest.raises(ValueError, match="PubMed"):
        StudyRow(rsid="rs1", pmid="https://www.ncbi.nlm.nih.gov/snp/rs1229984")


def test_studyrow_still_rejects_empty() -> None:
    with pytest.raises(ValueError, match="empty"):
        StudyRow(rsid="rs1", pmid="   ")
