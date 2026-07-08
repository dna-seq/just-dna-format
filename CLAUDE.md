# Agent Guidelines — just-dna-format

This repo is a **uv workspace** publishing two libraries: **`just-dna-format`** (the schema contract
— pydantic models for the authored spec DSL and the compiled `manifest.json`, plus integrity/
identity helpers, costing only `pydantic`) and **`just-dna-compiler`** (the reference compiler that
transforms a validated spec into a three-parquet artifact + manifest, adding polars/duckdb). Any
consumer picks the tier it needs. There is **no app, no orchestration, and no network here** — those
live in `just-dna-pipelines` / `just-dna-lite` / `just-dna-marketplace`.

## Read these first, in this order

1. **[docs/CONSTITUTION.md](docs/CONSTITUTION.md) — the durable charter. READ IT BEFORE JUDGING OR
   CHANGING ANYTHING.** It is the source of truth for what these packages are, what they will never
   do, and the invariants every release upholds (declarative-not-code, no network, backward-compat
   within a major, integrity-as-identity, orthogonal axes, the vocabulary idiom, round-trip/
   idempotency, and requiredness compatibility). When a plan conflicts with it, it wins. **An audit
   or design review that has not read the Constitution is incomplete** — its compatibility rules
   (Principles 3, 7, 8) decide whether a proposed change is even legal.
2. **[docs/ROADMAP.md](docs/ROADMAP.md)** — plans (revised often) and the `1.0`-cleanup tracker.
3. **[docs/CHANGELOG.md](docs/CHANGELOG.md)** — what actually shipped, newest first (shared across the
   ecosystem repos that consume these libs).
4. **[docs/COMPILER.md](docs/COMPILER.md)** — the compiler's per-feature coverage table (which schema
   features are validated / materialized / computed).

## Coding standards

- **Dependency tiers are sacred** (CONSTITUTION Goal 2): never add a heavy dep to `just-dna-format`;
  the compiler's polars/duckdb stay in `just-dna-compiler`. Never pull Dagster / LLM SDKs / HF.
- **No network, inject-only** (Principle 2): the resolver never downloads; the caller injects any
  reference.
- Type hints mandatory; **pathlib** for paths; **absolute imports only**; **no inline imports** (a
  guarded module-level `try/except ImportError` for optional deps is the only exception).
- Pydantic 2 for all data models. Constrained vocabularies are `frozenset[str]` + a validator, never
  `Enum`/`Literal` (Principle 6).
- **Additive within a major** (Principles 3/8): new columns are optional; a required field is never
  demoted; anything that changes `artifact.digest` bytes (parquet column set/types) is major-only —
  *except* while a version is still unpublished, where the digest is not yet frozen.
- **Round-trip must stay lossless and idempotent** (Principle 7) — prove it with tests, don't assume.
- `uv run pytest` runs the suite. Use `uv sync` / `uv add`; **never** `uv pip install`.
- New markdown (except this file / `README`) goes in `docs/`.

## Related repos (read-only unless the task targets them)

`just-dna-pipelines` (compiler/discovery, depends on these libs), `just-dna-lite` (app + webui, the
reference consumer), `just-dna-marketplace` (catalog/storage/serving; consumes the `revalidate`/
`needs_upgrade` derivation these libs supply), `just-prs`.
