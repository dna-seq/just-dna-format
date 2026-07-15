"""
Identity and versioning (SPEC §6).

Identity is `namespace/name`. `name` keeps the DSL rule `^[a-z][a-z0-9_]*$`; `namespace` is an
owned account/org slug (lowercase alphanumeric with hyphens, e.g. `just-dna-seq`). Versions are
SemVer `MAJOR.MINOR.PATCH` for public ordering; the legacy `vN` directory convention maps
`v1 -> 1.0.0`, `v2 -> 2.0.0`.
"""

import re
from dataclasses import dataclass
from functools import total_ordering

NAME_PATTERN: re.Pattern[str] = re.compile(r"^[a-z][a-z0-9_]*$")
# Hyphens *separate* alphanumeric segments — no leading/trailing hyphen, no doubled hyphen (so
# `just-dna-seq` is valid but `just-dna-`/`a--b` are not; a slug is not a place to hide empty parts).
NAMESPACE_PATTERN: re.Pattern[str] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_VERSION_PATTERN: re.Pattern[str] = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
_LEGACY_PATTERN: re.Pattern[str] = re.compile(r"^v?(\d+)$")


def is_valid_name(name: str) -> bool:
    """Whether `name` matches the module name rule `^[a-z][a-z0-9_]*$`."""
    return bool(NAME_PATTERN.match(name))


def validate_name(name: str) -> str:
    """Return `name` if valid, else raise `ValueError`."""
    if not is_valid_name(name):
        raise ValueError(
            f"module name must be lowercase alphanumeric with underscores, got: {name!r}"
        )
    return name


def is_valid_namespace(namespace: str) -> bool:
    """Whether `namespace` is a valid account/org slug (lowercase alnum + hyphens)."""
    return bool(NAMESPACE_PATTERN.match(namespace))


def validate_namespace(namespace: str) -> str:
    """Return `namespace` if valid, else raise `ValueError`."""
    if not is_valid_namespace(namespace):
        raise ValueError(
            f"namespace must be lowercase alphanumeric with hyphens, got: {namespace!r}"
        )
    return namespace


def canonical_id(namespace: str, name: str, version: str) -> str:
    """Build the canonical id `namespace/name@version`."""
    return f"{namespace}/{name}@{version}"


@total_ordering
@dataclass(frozen=True)
class Version:
    """A parsed SemVer `MAJOR.MINOR.PATCH`, comparable and stringifiable."""

    major: int
    minor: int
    patch: int

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def as_tuple(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __lt__(self, other: "Version") -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return self.as_tuple < other.as_tuple


def parse_version(version: str) -> Version:
    """Parse a strict `MAJOR.MINOR.PATCH` string into a `Version`, else raise `ValueError`."""
    match = _VERSION_PATTERN.match(version)
    if match is None:
        raise ValueError(f"version must be MAJOR.MINOR.PATCH, got: {version!r}")
    return Version(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def is_valid_version(version: str) -> bool:
    """Whether `version` is a strict `MAJOR.MINOR.PATCH` string."""
    return bool(_VERSION_PATTERN.match(version))


def version_from_legacy(legacy: str) -> str:
    """Map a legacy integer or `vN` directory name to SemVer (`v1`/`1` -> `1.0.0`)."""
    match = _LEGACY_PATTERN.match(legacy)
    if match is None:
        raise ValueError(f"legacy version must be an integer or vN, got: {legacy!r}")
    return f"{int(match.group(1))}.0.0"


def latest(versions: list[str]) -> str:
    """Return the highest SemVer string from a non-empty list."""
    if not versions:
        raise ValueError("cannot pick latest from an empty version list")
    return str(max((parse_version(v) for v in versions)))
