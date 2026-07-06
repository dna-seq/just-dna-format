"""Manifest contract tests (SPEC §4): round-trip and marketplace-field optionality."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from just_dna_format.integrity import build_artifact
from just_dna_format.manifest import (
    Compilation,
    Display,
    Identity,
    ModuleManifest,
    Stats,
    read_manifest,
    write_manifest,
)


def _manifest(tmp_path: Path) -> ModuleManifest:
    (tmp_path / "weights.parquet").write_bytes(b"w")
    artifact = build_artifact(tmp_path, ["weights.parquet"])
    return ModuleManifest(
        identity=Identity(
            namespace="just-dna-seq",
            name="longevity_variants_2026",
            version="2.0.0",
            canonical_id="just-dna-seq/longevity_variants_2026@2.0.0",
        ),
        display=Display(
            title="Longevity Variants 2026",
            description="Rare protective variants...",
            report_title="Familial Longevity",
            icon="heart-pulse",
            color="#21ba45",
        ),
        stats=Stats(variant_count=16, study_count=5, gene_count=8, genes=["CGAS", "TERT"],
                    categories=["cGAS-STING pathway"]),
        compilation=Compilation(compile_success=True, compiled_by="marketplace-server"),
        artifact=artifact,
    )


def test_manifest_roundtrips_through_disk(tmp_path: Path) -> None:
    original = _manifest(tmp_path)
    path = write_manifest(original, tmp_path / "manifest.json")
    loaded = read_manifest(path)
    assert loaded == original
    assert loaded.identity.canonical_id == "just-dna-seq/longevity_variants_2026@2.0.0"
    assert loaded.stats.genes == ["CGAS", "TERT"]


def test_marketplace_fields_default_to_none() -> None:
    # A compile-time manifest need not carry namespace/version/owner yet.
    manifest = ModuleManifest(
        identity=Identity(name="demo"),
        display=Display(title="Demo", description="d", report_title="r"),
        artifact={"digest": "sha256:00", "files": []},
    )
    assert manifest.identity.namespace is None
    assert manifest.identity.version is None
    assert manifest.owner is None
    assert manifest.stats.variant_count == 0
    assert manifest.compilation.compile_success is False
    assert manifest.manifest_version == "1.0"


def test_identity_enforces_name_namespace_version_rules() -> None:
    # Mirrors just-dna-pipelines model validation for the same values.
    with pytest.raises(ValidationError):
        Identity(name="Has_Caps")
    with pytest.raises(ValidationError):
        Identity(name="demo", namespace="With_Underscore")
    with pytest.raises(ValidationError):
        Identity(name="demo", version="2.0")  # not MAJOR.MINOR.PATCH


def test_display_enforces_hex_color() -> None:
    with pytest.raises(ValidationError):
        Display(title="t", description="d", report_title="r", color="red")
