# just-dna-compiler

The reference **compiler** for just-dna annotation modules: it turns an authored spec directory into
a deployable parquet artifact **plus a `manifest.json`** with integrity digests.

A module **composes from optional table kinds**: the only always-present file is `module_spec.yaml`.
A SNP module adds `variants.csv` (+ `studies.csv`, required whenever variants are present) → the
`weights` / `annotations` / `studies` parquets; a PGx / PharmGKB / PRS module instead carries only
its own table(s) (`diplotypes.csv`, `pharm_variants.csv`, `pgs.csv`, …) and needs no `variants.csv`.
Each present CSV materializes to its own parquet, so the artifact is the set of parquets the module
actually uses (up to twelve), not a fixed three.

It consumes the schema/contract from [`just-dna-format`](../schema) and is the shared transform
called by both `just-dna-pipelines` (local compile) and `just-dna-marketplace` (server-side
recompile on publish).

```python
from just_dna_compiler.compiler import validate_spec, compile_module

validate_spec(spec_dir)                       # -> ValidationResult (genes/categories lists)
compile_module(spec_dir, out_dir,             # -> CompilationResult (+ manifest.json written)
               resolve_with_ensembl=False,    # inject an Ensembl DuckDB/parquet dir to resolve
               compiled_by="marketplace-server")
```

**Dependencies:** `just-dna-format`, `polars`, `duckdb`, `pyyaml`, `platformdirs`, `python-dotenv` —
deliberately no Dagster / LLM SDKs. The Ensembl reference is **injected** by the caller (a `.duckdb`
file or a parquet dir); this package never downloads it.
