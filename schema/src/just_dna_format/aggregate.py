"""
Cross-version provenance aggregation (SPEC ROADMAP item 3).

Full provenance for a module is the *union of every version's* logs / provenance — "v3 provenance
= v1 + v2 + v3". The union semantics were defined in the format contract but had no helper; these
functions provide it so a consumer (e.g. the marketplace module-detail view) can present the
deduplicated set across versions without reimplementing the dedup rule.
"""

from typing import Iterable

from just_dna_format.manifest import FileEntry, ModuleManifest, Provenance


def aggregate_logs(manifests: Iterable[ModuleManifest]) -> list[FileEntry]:
    """Deduplicated union of `logs[]` across manifests.

    Dedup key is `(name, sha256)` — the same log path re-emitted unchanged across versions collapses
    to one entry, while a changed file at the same path is kept as a distinct entry. Ordering is
    stable: first occurrence wins, sorted by `(name, sha256)` for a deterministic result.
    """
    seen: dict[tuple[str, str], FileEntry] = {}
    for manifest in manifests:
        for entry in manifest.logs:
            seen.setdefault((entry.name, entry.sha256), entry)
    return [seen[key] for key in sorted(seen)]


def aggregate_provenance(manifests: Iterable[ModuleManifest]) -> list[Provenance]:
    """Deduplicated union of the per-version `provenance` summaries across manifests.

    Dedup key is the provenance document hash (`sha256`); a summary without a hash is keyed by a
    monotonic counter so distinct-but-unhashed summaries are not silently merged. Result is in
    **first-occurrence order** (the order manifests were passed) — deterministic, and not keyed on
    `id()` as before (object identity is non-reproducible across processes, so sorting by it gave a
    run-dependent order).
    """
    seen: dict[str, Provenance] = {}
    unhashed = 0
    for manifest in manifests:
        prov = manifest.provenance
        if prov is None:
            continue
        if prov.sha256:
            key = prov.sha256
        else:
            key = f"unhashed:{unhashed}"
            unhashed += 1
        seen.setdefault(key, prov)
    return list(seen.values())
