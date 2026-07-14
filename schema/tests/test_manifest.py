"""Manifest contract tests (SPEC §4): round-trip and marketplace-field optionality."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from just_dna_format.integrity import build_artifact
from just_dna_format.manifest import (
    Compilation,
    Contribution,
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


# ── RM14: structured per-version authorship (docs/USE_CASES.md §5a) ─────────────


def test_contribution_role_is_a_closed_vocab() -> None:
    assert Contribution(who="x", role="audited", kind=["human_certified"]).role == "audited"
    with pytest.raises(ValidationError):
        Contribution(who="x", role="approved", kind=["human"])  # not in the role vocab


def test_contribution_kind_is_open_multivalued_and_normalized() -> None:
    # Tags are lowercased, stripped, de-duplicated in order; unknown tags are KEPT (open set).
    c = Contribution(who="lab-swarm", role="created", kind=["AI", " swarm ", "ai", "gpt5-scale"])
    assert c.kind == ["ai", "swarm", "gpt5-scale"]
    # kind must carry at least one tag, and tags must be non-empty.
    with pytest.raises(ValidationError):
        Contribution(who="x", role="created", kind=[])
    with pytest.raises(ValidationError):
        Contribution(who="x", role="created", kind=["  "])


def test_contribution_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Contribution(who="x", role="created", kind=["human"], reviwer="typo")  # noqa: unexpected field


def test_authorship_survives_manifest_write_read(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    # A joint ("hybrid") contribution is TWO entries — a human expert and an ai swarm — same role.
    manifest.authorship = [
        Contribution(who="just-dna-agents@1.4", role="created", kind=["ai", "agent"], at="2026-07-12"),
        Contribution(who="Dr. A. Geneticist", role="audited", kind=["human_certified"]),
        Contribution(who="claude-opus-4-8", role="audited", kind=["ai", "swarm"]),
    ]
    write_manifest(manifest, tmp_path / "manifest.json")
    reloaded = read_manifest(tmp_path / "manifest.json")
    assert [c.who for c in reloaded.authorship] == [
        "just-dna-agents@1.4", "Dr. A. Geneticist", "claude-opus-4-8"
    ]
    audited = [c for c in reloaded.authorship if c.role == "audited"]
    assert {"human_certified"} == set(audited[0].kind)
    assert audited[1].kind == ["ai", "swarm"]


def test_authorship_defaults_to_empty_list(tmp_path: Path) -> None:
    # Optional and backward-compatible: an older manifest with no authorship still validates.
    assert _manifest(tmp_path).authorship == []
