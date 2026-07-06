# just-dna-module

The declarative **manifest contract** and **integrity primitives** for just-dna annotation
modules. Dependency-light (Pydantic + stdlib only) so it can be shared as the single source of
truth by both:

- **`just-dna-pipelines`** — *emits* `manifest.json` when it compiles a module, and
- **`just-dna-marketplace`** — *indexes, serves, and verifies* those manifests.

Keeping the contract in one small package prevents the two sides from drifting.

## What's here

| Module | Contents |
|---|---|
| `just_dna_module.manifest` | `ModuleManifest` + sub-models (`Identity`, `Display`, `Stats`, `Compilation`, `FileEntry`, `Artifact`); `read_manifest` / `write_manifest`. Mirrors the marketplace SPEC §4. |
| `just_dna_module.integrity` | `sha256_file`, `artifact_digest` (canonical Merkle root), `build_artifact`, `verify_manifest` (verify-then-install), `IntegrityError`. SPEC §5. |
| `just_dna_module.identity` | Name/namespace rules, `canonical_id`, SemVer `Version` + `parse_version`, `version_from_legacy` (`vN → N.0.0`), `latest`. SPEC §6. |

## Usage

```python
from just_dna_module.manifest import ModuleManifest, read_manifest
from just_dna_module.integrity import build_artifact, verify_manifest

# Compiler side: hash outputs and record the digest.
artifact = build_artifact(output_dir, ["weights.parquet", "annotations.parquet", "studies.parquet"])

# Downloader side: verify before installing (raises IntegrityError on any mismatch).
verify_manifest(module_dir, read_manifest(module_dir / "manifest.json"))
```

All hashes are SHA-256, lowercase hex, prefixed `sha256:`. The `artifact.digest` is a Merkle-style
root over the canonical file listing — verifying it verifies the whole set and is the version's
immutable content identity.

## Develop

```
uv sync
uv run pytest -vvv
```
