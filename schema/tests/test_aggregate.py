"""Cross-version log aggregation (ROADMAP item 3): full provenance = union of every version's logs."""

from typing import Optional

from just_dna_format.aggregate import aggregate_logs, aggregate_provenance
from just_dna_format.manifest import (
    Artifact,
    Display,
    FileEntry,
    Identity,
    ModuleManifest,
    Provenance,
)


def _manifest(
    logs: Optional[list[FileEntry]] = None, provenance: Optional[Provenance] = None
) -> ModuleManifest:
    return ModuleManifest(
        identity=Identity(name="m"),
        display=Display(title="t", description="d", report_title="r"),
        artifact=Artifact(digest="sha256:" + "00" * 32),
        logs=logs or [],
        provenance=provenance,
    )


def test_aggregate_is_deduplicated_union() -> None:
    run_v1 = FileEntry(name="run.log", sha256="sha256:aa", size=1)
    reviewer = FileEntry(name="logs/reviewer.log", sha256="sha256:bb", size=2)
    run_v3 = FileEntry(name="run.log", sha256="sha256:cc", size=3)  # same path, changed bytes

    v1 = _manifest([run_v1])
    v2 = _manifest([run_v1, reviewer])  # re-emits run_v1 unchanged + adds reviewer
    v3 = _manifest([run_v3, reviewer])  # run.log changed; reviewer unchanged

    result = aggregate_logs([v1, v2, v3])
    got = {(e.name, e.sha256) for e in result}
    assert got == {
        ("run.log", "sha256:aa"),          # v1/v2 run.log
        ("run.log", "sha256:cc"),          # v3 run.log (distinct bytes → kept)
        ("logs/reviewer.log", "sha256:bb"),  # collapsed across v2+v3
    }


def test_aggregate_empty() -> None:
    assert aggregate_logs([_manifest([]), _manifest([])]) == []


# ── aggregate_provenance (the higher-risk half: hashed rows collapse, unhashed stay distinct) ──


def test_aggregate_provenance_collapses_by_hash() -> None:
    shared = Provenance(generator="agent", item_count=3, file="provenance.json", sha256="sha256:pp")
    v1 = _manifest(provenance=shared)
    v2 = _manifest(provenance=shared)          # same doc re-emitted unchanged → one entry
    v3_prov = Provenance(generator="agent2", item_count=5, file="provenance.json", sha256="sha256:qq")
    v3 = _manifest(provenance=v3_prov)         # changed doc → distinct entry

    result = aggregate_provenance([v1, v2, v3])
    assert {p.sha256 for p in result} == {"sha256:pp", "sha256:qq"}
    assert len(result) == 2


def test_aggregate_provenance_keeps_unhashed_summaries_distinct() -> None:
    # Two summaries with no hash must NOT be silently merged (they are keyed by identity).
    a = Provenance(generator="a", item_count=1)
    b = Provenance(generator="b", item_count=2)
    result = aggregate_provenance([_manifest(provenance=a), _manifest(provenance=b)])
    assert len(result) == 2
    assert {p.generator for p in result} == {"a", "b"}


def test_aggregate_provenance_skips_absent() -> None:
    assert aggregate_provenance([_manifest(), _manifest()]) == []
