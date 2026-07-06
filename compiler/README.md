# just-dna-compiler

The reference **compiler** for just-dna annotation modules: it turns an authored spec directory
(`module_spec.yaml` + `variants.csv` + `studies.csv`) into the deployable three-parquet artifact
(`weights` / `annotations` / `studies`) **plus a `manifest.json`** with integrity digests.

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

**Dependencies:** `just-dna-format`, `polars`, `duckdb`, `pyyaml` — deliberately no Dagster / LLM
SDKs. The Ensembl reference is **injected** by the caller (a `.duckdb` file or a parquet dir); this
package never downloads it.
