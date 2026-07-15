"""
just-dna-compiler — the reference transform from an authored module spec directory to a composed
multi-parquet artifact (the three-parquet SNP core plus one parquet per optional 0.4 table kind)
plus its `manifest.json`.

Consumes the schema/contract from `just-dna-format`; both `just-dna-pipelines` (local compile) and
`just-dna-marketplace` (server-side recompile on publish) call the same `compile_module`.

    from just_dna_compiler.compiler import validate_spec, compile_module, reverse_module
"""
