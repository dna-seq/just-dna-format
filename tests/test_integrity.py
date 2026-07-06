"""Integrity tests (SPEC §13): digest stability/order-independence and tamper detection."""

import hashlib
from pathlib import Path

import pytest

from just_dna_module.integrity import (
    IntegrityError,
    artifact_digest,
    build_artifact,
    file_entries,
    sha256_bytes,
    sha256_file,
    verify_manifest,
)
from just_dna_module.manifest import (
    MARKETPLACE_COMPILED_BY,
    Artifact,
    Compilation,
    Display,
    FileEntry,
    Identity,
    ModuleManifest,
    Stats,
)


def _write(path: Path, data: bytes) -> None:
    path.write_bytes(data)


def _module_dir(tmp_path: Path) -> Path:
    """A minimal compiled-module directory with three artifact files."""
    (tmp_path / "weights.parquet").write_bytes(b"weights-bytes")
    (tmp_path / "annotations.parquet").write_bytes(b"annotation-bytes-longer")
    (tmp_path / "studies.parquet").write_bytes(b"studies")
    return tmp_path


def _manifest_for(module_dir: Path, *, compiled_by: str = MARKETPLACE_COMPILED_BY,
                  compile_success: bool = True) -> ModuleManifest:
    artifact = build_artifact(
        module_dir, ["weights.parquet", "annotations.parquet", "studies.parquet"]
    )
    return ModuleManifest(
        identity=Identity(name="demo"),
        display=Display(title="Demo", description="d", report_title="Demo Report"),
        stats=Stats(),
        compilation=Compilation(
            compile_success=compile_success, compiled_by=compiled_by
        ),
        artifact=artifact,
    )


def test_sha256_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    _write(path, b"hello world")
    assert sha256_file(path) == "sha256:" + hashlib.sha256(b"hello world").hexdigest()
    assert sha256_bytes(b"hello world") == sha256_file(path)


def test_artifact_digest_is_order_independent() -> None:
    a = FileEntry(name="a.parquet", sha256="sha256:aa", size=1)
    b = FileEntry(name="b.parquet", sha256="sha256:bb", size=2)
    c = FileEntry(name="c.parquet", sha256="sha256:cc", size=3)
    assert artifact_digest([a, b, c]) == artifact_digest([c, a, b])


def test_artifact_digest_changes_when_a_hash_changes() -> None:
    a = FileEntry(name="a.parquet", sha256="sha256:aa", size=1)
    b = FileEntry(name="b.parquet", sha256="sha256:bb", size=2)
    tampered = FileEntry(name="b.parquet", sha256="sha256:bX", size=2)
    assert artifact_digest([a, b]) != artifact_digest([a, tampered])


def test_verify_manifest_passes_on_untampered_module(tmp_path: Path) -> None:
    module_dir = _module_dir(tmp_path)
    manifest = _manifest_for(module_dir)
    # Should not raise.
    verify_manifest(module_dir, manifest)


def test_verify_detects_single_tampered_byte(tmp_path: Path) -> None:
    module_dir = _module_dir(tmp_path)
    manifest = _manifest_for(module_dir)
    # Flip one byte of one artifact after the manifest was built.
    (module_dir / "annotations.parquet").write_bytes(b"annotation-bytes-longeX")
    with pytest.raises(IntegrityError, match="hash mismatch"):
        verify_manifest(module_dir, manifest)


def test_verify_detects_digest_mismatch(tmp_path: Path) -> None:
    module_dir = _module_dir(tmp_path)
    manifest = _manifest_for(module_dir)
    # Corrupt the declared digest but leave per-file hashes intact.
    manifest.artifact.digest = "sha256:deadbeef"
    with pytest.raises(IntegrityError, match="digest mismatch"):
        verify_manifest(module_dir, manifest)


def test_verify_rejects_missing_artifact_file(tmp_path: Path) -> None:
    module_dir = _module_dir(tmp_path)
    manifest = _manifest_for(module_dir)
    (module_dir / "studies.parquet").unlink()
    with pytest.raises(IntegrityError, match="missing on disk"):
        verify_manifest(module_dir, manifest)


def test_verify_rejects_foreign_compiler(tmp_path: Path) -> None:
    module_dir = _module_dir(tmp_path)
    manifest = _manifest_for(module_dir, compiled_by="someone-else")
    with pytest.raises(IntegrityError, match="untrusted"):
        verify_manifest(module_dir, manifest)
    # But passes when the caller opts out of the marketplace trust check.
    verify_manifest(module_dir, manifest, require_marketplace=False)


def test_verify_rejects_failed_compile(tmp_path: Path) -> None:
    module_dir = _module_dir(tmp_path)
    manifest = _manifest_for(module_dir, compile_success=False)
    with pytest.raises(IntegrityError, match="compile_success"):
        verify_manifest(module_dir, manifest)


def test_check_inputs_verifies_spec_files(tmp_path: Path) -> None:
    module_dir = _module_dir(tmp_path)
    (module_dir / "variants.csv").write_bytes(b"rsid,weight\nrs1,0.5\n")
    manifest = _manifest_for(module_dir)
    manifest.inputs = file_entries(module_dir, ["variants.csv"])
    verify_manifest(module_dir, manifest, check_inputs=True)
    # Tamper the input and the input check should fail.
    (module_dir / "variants.csv").write_bytes(b"rsid,weight\nrs1,0.9\n")
    with pytest.raises(IntegrityError, match="input hash mismatch"):
        verify_manifest(module_dir, manifest, check_inputs=True)
