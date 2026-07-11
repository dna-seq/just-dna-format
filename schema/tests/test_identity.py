"""Identity and versioning tests (SPEC §6)."""

import pytest

from just_dna_format.identity import (
    Version,
    canonical_id,
    is_valid_name,
    is_valid_namespace,
    latest,
    parse_version,
    validate_name,
    version_from_legacy,
)


@pytest.mark.parametrize(
    "name,valid",
    [
        ("longevity_variants_2026", True),
        ("coronary", True),
        ("a1", True),
        ("1abc", False),      # must start with a letter
        ("Has_Caps", False),
        ("has-hyphen", False),  # hyphens are for namespaces, not names
        ("", False),
    ],
)
def test_name_rule(name: str, valid: bool) -> None:
    assert is_valid_name(name) is valid


def test_validate_name_raises_on_bad() -> None:
    with pytest.raises(ValueError):
        validate_name("Bad Name")


@pytest.mark.parametrize(
    "ns,valid",
    [("just-dna-seq", True), ("antonkulaga", True), ("With_Underscore", False), ("-lead", False)],
)
def test_namespace_rule(ns: str, valid: bool) -> None:
    assert is_valid_namespace(ns) is valid


def test_canonical_id() -> None:
    assert (
        canonical_id("just-dna-seq", "longevity_variants_2026", "2.0.0")
        == "just-dna-seq/longevity_variants_2026@2.0.0"
    )


def test_version_ordering() -> None:
    assert parse_version("1.0.0") < parse_version("2.0.0")
    assert parse_version("1.2.0") < parse_version("1.10.0")  # numeric, not lexical
    assert parse_version("2.0.0") == Version(2, 0, 0)
    assert str(parse_version("3.4.5")) == "3.4.5"


def test_parse_version_rejects_non_semver() -> None:
    for bad in ["1.0", "v1.0.0", "1.0.0-rc1", "x.y.z", ""]:
        with pytest.raises(ValueError):
            parse_version(bad)


@pytest.mark.parametrize("legacy,expected", [("v1", "1.0.0"), ("v2", "2.0.0"), ("3", "3.0.0")])
def test_legacy_mapping(legacy: str, expected: str) -> None:
    assert version_from_legacy(legacy) == expected


def test_legacy_mapping_rejects_bad_input() -> None:
    for bad in ["release-1", "v", "1.2", ""]:
        with pytest.raises(ValueError):
            version_from_legacy(bad)


def test_latest_picks_highest() -> None:
    assert latest(["1.0.0", "2.0.0", "1.10.0", "1.2.0"]) == "2.0.0"
    with pytest.raises(ValueError):
        latest([])
