# just-dna-format

The **module format** for just-dna annotation modules — the declarative schema/contract and its
reference compiler — as a uv workspace publishing two packages:

| Package | Path | What it is | Deps |
|---|---|---|---|
| [`just-dna-format`](schema) | `schema/` | The schema + integrity contract: the authored DSL spec, the compiled `manifest.json`, digests, identity/versioning. | Pydantic + stdlib |
| [`just-dna-compiler`](compiler) | `compiler/` | The transform: spec directory → three-parquet artifact + `manifest.json`. | + polars, duckdb, pyyaml |

**Why two packages, one repo.** `just-dna-format` stays dependency-light so *anyone* — a thin API,
a webui client, a downloader that only verifies a digest — can depend on it for the cost of
`pydantic`. The compiler's polars/duckdb weight lives in `just-dna-compiler`. Consumers pick the
tier they need:

- verify-only client → `just-dna-format`
- compile / recompile (marketplace, pipelines) → `just-dna-compiler` (pulls `just-dna-format`)
- neither pulls Dagster or LLM SDKs — those stay in `just-dna-pipelines`.

Co-locating them keeps the schema and the compiler that targets it in one place (no cross-repo
fetch to understand the contract), while uv still builds/publishes two independent distributions.

## Develop

```bash
uv sync              # installs both members + dev tools into one workspace venv
uv run pytest        # runs schema/ and compiler/ test suites
```

Build both distributions: `uv build --all-packages`.

## Design docs

- [`docs/CONSTITUTION.md`](docs/CONSTITUTION.md) — the durable charter: goals, non-goals, and the
  invariants every release upholds (declarative-not-code, no-network, backward-compat-within-a-major,
  integrity). Amended only deliberately.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — what shipped and what's planned (including the 0.3 schema
  brief and the 1.0-cleanup tracker). Revised often.
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — release history.
- [`docs/COMPILER.md`](docs/COMPILER.md) — how much of the 0.3 schema the compiler covers: the
  validator is complete, some computed items are intentionally deferred (a partial-conformance table).
- [`docs/REFERENCE_EXAMPLES.md`](docs/REFERENCE_EXAMPLES.md) — illustrative worked module drafts
  (simple SNV, APOE diplotype, G6PD hemizygous, SMN1 copy-number, CYP2D6 star-alleles). Ideas/drafts
  for authors and consumers, **not** a shipped contract.
