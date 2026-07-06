"""compile_module captures optional run/provenance logs into the module dir + manifest."""

import hashlib
from pathlib import Path

import yaml
from just_dna_format.integrity import verify_manifest
from just_dna_format.manifest import read_manifest

from just_dna_compiler.compiler import compile_module

_YAML = {
    "schema_version": "1.0",
    "module": {"name": "demo_mod", "title": "T", "description": "D", "report_title": "R"},
}
_VARIANTS = "rsid,genotype,weight,state,conclusion,gene,category\nrs1,A/G,0.1,neutral,ok,G,c\n"
_STUDIES = "rsid,pmid,population,p_value,conclusion,study_design\nrs1,1,T,0.05,E,U\n"


def _spec(tmp_path: Path, *, with_logs: bool) -> Path:
    spec = tmp_path / "spec"
    spec.mkdir(parents=True)
    (spec / "module_spec.yaml").write_text(yaml.dump(_YAML))
    (spec / "variants.csv").write_text(_VARIANTS)
    (spec / "studies.csv").write_text(_STUDIES)
    if with_logs:
        (spec / "run.log").write_text("aggregate run transcript\n")
        (spec / "logs").mkdir()
        (spec / "logs" / "researcher.log").write_text("researcher reasoning\n")
        (spec / "logs" / "reviewer.log").write_text("reviewer verdict\n")
    return spec


def test_no_logs_is_valid(tmp_path: Path) -> None:
    out = tmp_path / "out"
    manifest = compile_module(_spec(tmp_path, with_logs=False), out, resolve_with_ensembl=False).manifest
    assert manifest is not None and manifest.logs == []


def test_logs_discovered_copied_and_hashed(tmp_path: Path) -> None:
    spec = _spec(tmp_path, with_logs=True)
    out = tmp_path / "out"
    manifest = compile_module(spec, out, resolve_with_ensembl=False,
                              compiled_by="marketplace-server").manifest
    assert manifest is not None
    by_name = {e.name: e for e in manifest.logs}
    assert set(by_name) == {"run.log", "logs/researcher.log", "logs/reviewer.log"}

    # Files were copied into the module dir, preserving the logs/ subfolder.
    assert (out / "run.log").is_file()
    assert (out / "logs" / "reviewer.log").is_file()

    # Hashes match the source bytes.
    expected = "sha256:" + hashlib.sha256((spec / "logs" / "reviewer.log").read_bytes()).hexdigest()
    assert by_name["logs/reviewer.log"].sha256 == expected

    # Logs are not part of the compiled-artifact digest.
    assert all(f.name.endswith(".parquet") for f in manifest.artifact.files)

    # Full verify (incl. logs) passes on the untampered module.
    verify_manifest(out, read_manifest(out / "manifest.json"), check_logs=True)


def test_logs_do_not_change_artifact_digest(tmp_path: Path) -> None:
    # Compile the same spec twice, once with logs and once without: identical artifact digest.
    without = compile_module(_spec(tmp_path / "a", with_logs=False), tmp_path / "oa",
                             resolve_with_ensembl=False).manifest
    with_logs = compile_module(_spec(tmp_path / "b", with_logs=True), tmp_path / "ob",
                               resolve_with_ensembl=False).manifest
    assert without.artifact.digest == with_logs.artifact.digest
