"""Optional per-version log files in the manifest (hashed, not part of artifact.digest)."""

from pathlib import Path

import pytest

from just_dna_format.integrity import (
    IntegrityError,
    build_artifact,
    file_entries,
    verify_manifest,
)
from just_dna_format.manifest import (
    Compilation,
    Display,
    Identity,
    ModuleManifest,
    read_manifest,
    write_manifest,
)


def _module(tmp_path: Path, *, with_logs: bool) -> ModuleManifest:
    (tmp_path / "weights.parquet").write_bytes(b"w")
    logs = []
    if with_logs:
        (tmp_path / "run.log").write_bytes(b"aggregate run transcript\n")
        (tmp_path / "logs").mkdir()
        (tmp_path / "logs" / "researcher.log").write_bytes(b"researcher reasoning\n")
        (tmp_path / "logs" / "reviewer.log").write_bytes(b"reviewer verdict\n")
        logs = file_entries(tmp_path, ["run.log", "logs/researcher.log", "logs/reviewer.log"])
    return ModuleManifest(
        identity=Identity(name="demo"),
        display=Display(title="Demo", description="d", report_title="R"),
        compilation=Compilation(compile_success=True, compiled_by="marketplace-server"),
        artifact=build_artifact(tmp_path, ["weights.parquet"]),
        logs=logs,
    )


def test_logs_default_empty_and_valid(tmp_path: Path) -> None:
    m = _module(tmp_path, with_logs=False)
    assert m.logs == []
    verify_manifest(tmp_path, m, check_logs=True)  # no logs -> still valid


def test_logs_roundtrip_including_subfolder(tmp_path: Path) -> None:
    m = _module(tmp_path, with_logs=True)
    loaded = read_manifest(write_manifest(m, tmp_path / "manifest.json"))
    names = {e.name for e in loaded.logs}
    assert names == {"run.log", "logs/researcher.log", "logs/reviewer.log"}  # per-role preserved


def test_logs_excluded_from_artifact_digest(tmp_path: Path) -> None:
    # Same compiled data, different logs -> identical artifact.digest (dedup stays intact).
    da = tmp_path / "da"; da.mkdir(); (da / "weights.parquet").write_bytes(b"w")
    db = tmp_path / "db"; db.mkdir(); (db / "weights.parquet").write_bytes(b"w")
    (db / "run.log").write_bytes(b"different log")
    assert build_artifact(da, ["weights.parquet"]).digest == build_artifact(
        db, ["weights.parquet"]
    ).digest  # logs never entered the digest


def test_check_logs_verifies_present_and_skips_absent(tmp_path: Path) -> None:
    m = _module(tmp_path, with_logs=True)
    verify_manifest(tmp_path, m, check_logs=True)  # all present + matching
    # Removing an optional log must NOT fail verification.
    (tmp_path / "logs" / "reviewer.log").unlink()
    verify_manifest(tmp_path, m, check_logs=True)


def test_check_logs_detects_tamper(tmp_path: Path) -> None:
    m = _module(tmp_path, with_logs=True)
    (tmp_path / "logs" / "researcher.log").write_bytes(b"tampered reasoning\n")
    with pytest.raises(IntegrityError, match="log hash mismatch"):
        verify_manifest(tmp_path, m, check_logs=True)
    # Default verify (check_logs=False) ignores logs entirely.
    verify_manifest(tmp_path, m)
