"""
Integrity primitives (SPEC §5).

All hashes are SHA-256, lowercase hex, prefixed `sha256:`. These functions are the shared
implementation the compiler uses to *emit* integrity fields and a downloader uses to *verify*
them — keeping both sides byte-for-byte agreement by construction.

Time is never read here: callers pass any timestamps into the manifest. This keeps the module
pure and deterministic.
"""

import hashlib
import json
from pathlib import Path

from just_dna_module.manifest import (
    MARKETPLACE_COMPILED_BY,
    Artifact,
    FileEntry,
    ModuleManifest,
)

SHA256_PREFIX: str = "sha256:"
_CHUNK: int = 1 << 20  # 1 MiB streaming reads


class IntegrityError(Exception):
    """Raised when a file hash, artifact digest, or trust check fails verification."""


def sha256_bytes(data: bytes) -> str:
    """SHA-256 of raw bytes, prefixed `sha256:`."""
    return SHA256_PREFIX + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Streaming SHA-256 of a file's raw bytes, prefixed `sha256:`."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
    return SHA256_PREFIX + digest.hexdigest()


def file_entry(directory: Path, name: str) -> FileEntry:
    """Build a `FileEntry` (name, sha256, size) for `directory/name`."""
    path = Path(directory) / name
    return FileEntry(name=name, sha256=sha256_file(path), size=path.stat().st_size)


def file_entries(directory: Path, names: list[str]) -> list[FileEntry]:
    """Build `FileEntry` rows for each existing name under `directory` (skips missing)."""
    directory = Path(directory)
    return [file_entry(directory, name) for name in names if (directory / name).is_file()]


def artifact_digest(files: list[FileEntry]) -> str:
    """
    Merkle-style root over the file set (SPEC §5): build the JSON array
    `[{"name","sha256","size"}, ...]` sorted by name, serialized with sorted keys and no
    whitespace, then hash. Verifying this one digest verifies the whole set, and it is the
    version's immutable content identity — independent of the order files were listed in.
    """
    listing = sorted(
        ({"name": f.name, "sha256": f.sha256, "size": f.size} for f in files),
        key=lambda entry: entry["name"],
    )
    canonical = json.dumps(listing, sort_keys=True, separators=(",", ":"))
    return sha256_bytes(canonical.encode("utf-8"))


def build_artifact(output_dir: Path, filenames: list[str]) -> Artifact:
    """Hash each output file and compute the artifact digest over the set."""
    files = file_entries(output_dir, filenames)
    return Artifact(digest=artifact_digest(files), files=files)


def verify_manifest(
    module_dir: Path,
    manifest: ModuleManifest,
    *,
    require_marketplace: bool = True,
    check_inputs: bool = False,
) -> None:
    """
    Verify a downloaded module against its manifest (SPEC §5 verify-then-install).

    Steps:
      1. Every `artifact.files[]` present on disk hashes to its declared value.
      2. The recomputed `artifact.digest` matches the manifest.
      3. `compile_success` is true and `compiled_by == "marketplace-server"`
         (when `require_marketplace`).
      4. Optionally (`check_inputs`) every `inputs[]` file on disk matches its declared hash.

    Raises `IntegrityError` on the first failure; returns `None` on success.
    """
    module_dir = Path(module_dir)

    for entry in manifest.artifact.files:
        path = module_dir / entry.name
        if not path.is_file():
            raise IntegrityError(f"artifact file missing on disk: {entry.name}")
        actual = sha256_file(path)
        if actual != entry.sha256:
            raise IntegrityError(
                f"artifact hash mismatch for {entry.name}: "
                f"declared {entry.sha256}, computed {actual}"
            )

    recomputed = artifact_digest(manifest.artifact.files)
    if recomputed != manifest.artifact.digest:
        raise IntegrityError(
            f"artifact digest mismatch: declared {manifest.artifact.digest}, "
            f"computed {recomputed}"
        )

    if require_marketplace:
        if not manifest.compilation.compile_success:
            raise IntegrityError("compilation.compile_success is not true — untrusted")
        if manifest.compilation.compiled_by != MARKETPLACE_COMPILED_BY:
            raise IntegrityError(
                f"compiled_by is {manifest.compilation.compiled_by!r}, "
                f"expected {MARKETPLACE_COMPILED_BY!r} — untrusted"
            )

    if check_inputs:
        for entry in manifest.inputs:
            path = module_dir / entry.name
            if not path.is_file():
                raise IntegrityError(f"input file missing on disk: {entry.name}")
            actual = sha256_file(path)
            if actual != entry.sha256:
                raise IntegrityError(
                    f"input hash mismatch for {entry.name}: "
                    f"declared {entry.sha256}, computed {actual}"
                )
