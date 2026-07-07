"""Cross-version log aggregation (ROADMAP item 3): full provenance = union of every version's logs."""

from just_dna_format.aggregate import aggregate_logs
from just_dna_format.manifest import Artifact, Display, FileEntry, Identity, ModuleManifest


def _manifest(logs: list[FileEntry]) -> ModuleManifest:
    return ModuleManifest(
        identity=Identity(name="m"),
        display=Display(title="t", description="d", report_title="r"),
        artifact=Artifact(digest="sha256:" + "00" * 32),
        logs=logs,
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
