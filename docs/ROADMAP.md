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
| 6 | **Tighten `StudyRow.pmid` validation** | Today the only rule is "non-empty" (the pre-extraction `PMID_PATTERN` validator was commented out because existing modules didn't conform). Re-introduce structured validation — accept bare digits (`9545397`) and the legacy bracketed form (`[PMID: 9545397]; [PMID 123]`) via a `PMID_PATTERN`-style check — **after** auditing existing modules for conformance so it doesn't reject already-published data. Stays as-is for 0.1. |

## Non-goals for these packages

To keep the tiers clean, these libraries deliberately **do not** pull Dagster, LLM SDKs, or
HuggingFace, and do not download reference data. Orchestration/AI authoring live in
`just-dna-pipelines`; artifact storage/serving lives in `just-dna-marketplace`.

## Cross-repo follow-ups (tracked elsewhere)

- **just-dna-pipelines** — ✅ **done (2026-07-06)**: depends on `just-dna-format>=0.1.0` +
  `just-dna-compiler>=0.1.0`; `module_compiler` is now re-export shims over the libs (duplicate
  transform/schema deleted, `ensure_resolver_db` provisioning kept); `.json` added to
  `_SPEC_SUFFIXES`. See CHANGELOG.md 2026-07-06.
- **just-dna-marketplace** — add `just-dna-compiler` as the M4 publish dependency; serve `logs` via
  the files endpoint; aggregate cross-version provenance for the module detail view.

## Observations from the just-dna-lite integration (2026-07-06)

Surfaced while repointing just-dna-pipelines at the libs — flagged here so `-marketplace` and
`-agents` don't rediscover them:

1. **`validate_spec` stats keys were renamed** vs. the pre-extraction schema and are a de-facto
   contract: `unique_genes → gene_count`, `study_rows → study_count`, `unique_variants →
   variant_count`; `genes`/`categories` are now sorted lists filtering `None`. `unique_rsids` and
   `module_name` are unchanged. Any consumer that asserted on the old keys must update (just-dna-lite
   tests already did). Consider documenting the `stats` shape explicitly on `ValidationResult`.
2. **`VALID_PRIORITIES` and `PMID_PATTERN` were intentionally not carried into `just_dna_format.spec`.**
   Confirmed dead in the original schema: `VALID_PRIORITIES` was referenced by no validator (priority
   is free-form `Optional[str]`), and `PMID_PATTERN`'s validator was commented out (the live rule is
   only "pmid non-empty", which the lib preserves). Tightening PMID validation is planned as a 0.2
   item (see table row 6); it stays as-is for 0.1. Stricter priority validation would likewise be a
   new opt-in validator, not a restoration.
3. **Ensembl provisioning is not in the libs by design** (inject-only, ROADMAP item 4). just-dna-lite
   keeps `ensure_resolver_db` (HF download + DuckDB build) in `module_compiler/resolver.py` and injects
   the cache. `register_custom_module` and direct `resolve_variants` callers auto-provision via
   `ensure_resolver_db` (idempotent), preserving the pre-extraction convenience. The bare
   `compile_module` re-export and the `pipelines module compile` CLI stay inject-only: with no cache
   present they skip resolution with a warning rather than downloading.
