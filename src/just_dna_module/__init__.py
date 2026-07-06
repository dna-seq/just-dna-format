"""
just-dna-module — the declarative manifest contract and integrity primitives shared by
`just-dna-pipelines` (which emits manifests) and `just-dna-marketplace` (which indexes and
serves them).

Import from the submodules directly, e.g.::

    from just_dna_module.manifest import ModuleManifest
    from just_dna_module.integrity import sha256_file, artifact_digest, verify_manifest
    from just_dna_module.identity import parse_version, canonical_id
"""
