# just-dna-format

The declarative **schema + integrity contract** for just-dna annotation modules: both the authored
input DSL and the compiled `manifest.json`. Dependency-light (Pydantic + `cryptography`, for Ed25519
signature verification) so it can be shared as the single source of truth by:

- **`just-dna-compiler`** — the reference transform (spec → parquet artifact + manifest);
- **`just-dna-pipelines`** — *emits* `manifest.json` when it compiles a module;
- **`just-dna-marketplace`** — *indexes, serves, and verifies* those manifests;
- **`just-dna-agents`** — authoring support (renders `reference.authoring_reference()`).

Keeping the contract in one small package prevents the sides from drifting.

## What's here

| Module | Contents |
|---|---|
| `just_dna_format.spec` | The authored DSL: `ModuleSpecConfig`, `VariantRow`, `StudyRow`, `ModuleInfo`, `Defaults` (+ `extract_pmids`). |
| `just_dna_format.binning` | The measure→phenotype primitive: `MeasureBinRow` + `Activity/CopyNumber/RepeatAllele/Heteroplasmy` rows and `validate_bins` (0.4). |
| `just_dna_format.pgx` | PGx star-allele model: `HaplotypeRow`, `AlleleFunctionRow`, `DiplotypeRow`, `PharmVariantRow` (0.4). |
| `just_dna_format.pgs` | `PgsRow` — a curated PGS-Catalog interface with ancestry-validity fields (0.4). |
| `just_dna_format.vocab` | Shared constrained vocabularies, identifier grammars, and validator helpers. |
| `just_dna_format.derive` | Legacy `state`/ClinVar-boolean → 0.3-axis derivations (total, idempotent). |
| `just_dna_format.manifest` | `ModuleManifest` + sub-models (`Identity`, `Display`, `Stats`, `Compilation`, `FileEntry`, `Artifact`, `Provenance`, `Signature`, `GenePanelSpec`); `read_manifest` / `write_manifest`. SPEC §4. |
| `just_dna_format.integrity` | `sha256_file`, `artifact_digest` (canonical Merkle root), `build_artifact`, `verify_manifest`, `verify_signature`, `IntegrityError`. SPEC §5. |
| `just_dna_format.signing` | Ed25519 signing over `artifact.digest` (key management side). |
| `just_dna_format.aggregate` | Cross-version log / provenance union helpers. |
| `just_dna_format.reference` | `authoring_reference()` / `json_schemas()` — drift-proof DSL description generated from the live models. |
| `just_dna_format.identity` | Name/namespace rules, `canonical_id`, SemVer `Version` + `parse_version`, `version_from_legacy` (`vN → N.0.0`), `latest`. SPEC §6. |

## Usage

```python
from just_dna_format.manifest import ModuleManifest, read_manifest
from just_dna_format.integrity import build_artifact, verify_manifest

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
