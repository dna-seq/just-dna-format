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
