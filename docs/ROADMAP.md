# just-dna-format — Roadmap

This repo (a uv workspace publishing `just-dna-format` + `just-dna-compiler`) is the schema
contract and reference compiler for just-dna annotation modules. This doc tracks what shipped in
**0.1.0** and what's planned for **0.2**.

## Shipped in 0.1.0

- **`just-dna-format`** (schema, pydantic + stdlib): `spec` (authored DSL: `ModuleSpecConfig`,
  `VariantRow`, `StudyRow`, `ModuleInfo` extending `Display`), `manifest` (`ModuleManifest` +
  `Identity`/`Display`/`Stats`/`Compilation`/`FileEntry`/`Artifact`), `integrity` (`sha256_file`,
  `artifact_digest` Merkle root, `build_artifact`, `verify_manifest`), `identity` (name/namespace
  rules, SemVer, `canonical_id`, legacy `vN → N.0.0`).
- **`just-dna-compiler`** (transform, + polars/duckdb/pyyaml/platformdirs/dotenv): `validate_spec`,
  `compile_module` (emits `manifest.json` with input/artifact hashes + digest, `genes`/`categories`
  stats), `reverse_module`, and a pipelines-free Ensembl `resolver`.
- **Provenance logs**: optional per-version hashed log files (`ModuleManifest.logs`) — a top-level
  `*.log` plus a `logs/` per-role subtree — copied into the module dir, hashed like `inputs`, kept
  **out of `artifact.digest`**. Absent logs never invalidate; `verify_manifest(check_logs=True)`.
- **Ensembl cache reuse**: `just_dna_compiler.cache` mirrors just-dna-lite's layout
  (`$JUST_DNA_PIPELINES_CACHE_DIR/ensembl_variations/...`, `.env`-driven); never downloads.
- **Tests**: 82 passing (schema + compiler), incl. regression tests ported from just-dna-lite;
  Ensembl resolver tests are `@integration` (skip without a cache).

## Planned for 0.2

| # | Item | Notes |
|---|---|---|
| 1 | **Structured provenance** | Complement the 0.1 file-based logs with an optional `items[]` model keyed by `variant_key`/`rsid` (rationale, reviewer verdict, confidence, human-review flag), plus a lean `manifest.provenance` summary pointer (generator, model, agent/framework version, `item_count`, sha256) so catalog cards can flag "AI-authored · rationale available" without inlining full text. Additive/optional → no `schema_version` bump. |
| 2 | **Ed25519 signing** | SPEC §5 "future": sign `artifact.digest` with a server key, publish the pubkey, add an optional `signature` block to the manifest and a signature check in `verify_manifest`. Defends against a compromised storage backend. |
| 3 | **Cross-version log aggregation helper** | The union-of-logs semantics for full provenance (v3 = v1+v2+v3) are defined but there's no helper. Add a small function (given a set of version manifests) that returns the deduplicated log set across versions. |
| 4 | **Resolver cache provisioning** | Decide the story for building the Ensembl DuckDB from parquet in a decoupled way (a documented `build`/`ensure` helper), and whether to offer an opt-in fetch behind an explicit flag — vs. keeping the resolver strictly inject-only (current 0.1 stance, no network). |
| 5 | **ClinVar/quality flags in stats** *(maybe)* | `weights.parquet` carries `clinvar`/`pathogenic`/`benign`; `manifest.stats` does not summarize them. Consider surfacing counts if the marketplace wants to facet on them. Only if a real consumer needs it. |

## Non-goals for these packages

To keep the tiers clean, these libraries deliberately **do not** pull Dagster, LLM SDKs, or
HuggingFace, and do not download reference data. Orchestration/AI authoring live in
`just-dna-pipelines`; artifact storage/serving lives in `just-dna-marketplace`.

## Cross-repo follow-ups (tracked elsewhere)

- **just-dna-pipelines** — repoint its `module_compiler` to `just-dna-compiler` (re-export shim +
  delete the duplicate); add `.json` to `_SPEC_SUFFIXES` so `manifest.json` survives install.
- **just-dna-marketplace** — add `just-dna-compiler` as the M4 publish dependency; serve `logs` via
  the files endpoint; aggregate cross-version provenance for the module detail view.
