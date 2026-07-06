"""
just-dna-format — the declarative schema + integrity contract for just-dna annotation modules.

Covers both halves of the module format: the authored input DSL (`spec`) and the compiled output
`manifest` (+ integrity digests and identity/versioning rules). Dependency-light (Pydantic +
stdlib) so it is shared by `just-dna-compiler` (which emits manifests), `just-dna-pipelines`, and
`just-dna-marketplace` (which indexes and serves them) without pulling heavy transitive deps.

Import from the submodules directly, e.g.::

    from just_dna_format.spec import ModuleSpecConfig, VariantRow, StudyRow
    from just_dna_format.manifest import ModuleManifest
    from just_dna_format.integrity import sha256_file, artifact_digest, verify_manifest
    from just_dna_format.identity import parse_version, canonical_id
"""
