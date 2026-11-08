import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

spec = importlib.util.spec_from_file_location("package_release", Path(__file__).parents[1]/"scripts/package_release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.fixture
def project(tmp_path):
    root = tmp_path/"project"
    root.mkdir()
    (root/"README.md").write_text("A test-only project.\n")
    (root/"pyproject.toml").write_text('[project]\nname="test-only"\n')
    (root/"data").mkdir()
    (root/"data/evidence.json").write_text('{"test_only": true}\n')
    return root


def test_release_is_deterministic_and_preserves_evidence_but_excludes_clutter(project, tmp_path):
    for folder in ("work", "build", ".venv", "data/__pycache__", "src/project.egg-info"):
        (project/folder).mkdir(parents=True, exist_ok=True)
        (project/folder/"clutter.txt").write_text("Not a deliverable.")
    (project/".env").write_text("PRIVATE_SETTING=do-not-package")
    (project/"data/budget.json.lock").write_text("lock")
    (project/"data/paper.aux").write_text("TeX build state")
    (project/"data/paper.synctex.gz").write_bytes(b"TeX source map")
    first, second = tmp_path/"a.zip", tmp_path/"b.zip"
    a = release.build_release(project, first)
    b = release.build_release(project, second)
    assert a["sha256"] == b["sha256"]
    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert len(names) == 4
        assert archive.read("sycophancy-confidence/data/evidence.json") == (project/"data/evidence.json").read_bytes()
    assert release.verify_release(first)["verification"] == "passed"


def test_release_rejects_modified_frozen_research_inputs(project, tmp_path):
    (project/"data/verification").mkdir()
    (project/"data/verification/main_design.json").write_text(json.dumps({"files": {"data/evidence.json": "wrong"}}))
    with pytest.raises(ValueError, match="Frozen research input"):
        release.build_release(project, tmp_path/"bad.zip")


def test_release_rejects_recognizable_credentials_without_printing_value(project, tmp_path):
    (project/"data/key.txt").write_text("sk-" + "a"*30)
    with pytest.raises(ValueError, match="Possible credential in release input: data/key.txt"):
        release.build_release(project, tmp_path/"bad.zip")


def test_opaque_reasoning_does_not_trigger_plaintext_key_pattern(project, tmp_path):
    path = project / "data/challenge_v1/run/responses.jsonl"
    path.parent.mkdir(parents=True)
    token = "gAAAAA" + "Q" * 150 + "sk-" + "a" * 30 + "=="
    row = {"provider_raw_response": {"output": [{"type": "reasoning", "encrypted_content": token}]}}
    raw = (json.dumps(row) + "\n").encode()
    path.write_bytes(raw)
    archive = tmp_path / "opaque.zip"
    release.build_release(project, archive)
    with zipfile.ZipFile(archive) as package:
        assert package.read("sycophancy-confidence/data/challenge_v1/run/responses.jsonl") == raw
    row["response"] = "sk-" + "b" * 30
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError, match="Possible credential"):
        release.build_release(project, tmp_path / "key.zip")


@pytest.mark.parametrize("kind,token", [
    ("reasoning", "sk-" + "c" * 30),
    ("message", "gAAAAA" + "Q" * 150 + "sk-" + "c" * 30),
])
def test_encrypted_field_does_not_hide_plain_keys_or_other_output_types(kind, token):
    raw = json.dumps({"provider_raw_response": {"output": [{"type": kind, "encrypted_content": token}]}}).encode()
    assert release.possible_credential(raw, "data/challenge_v1/run/responses.jsonl")


def test_verification_rejects_archive_content_tampering(project, tmp_path):
    good, bad = tmp_path/"good.zip", tmp_path/"bad.zip"
    release.build_release(project, good)
    with zipfile.ZipFile(good) as original, zipfile.ZipFile(bad, "w") as changed:
        for info in original.infolist():
            raw = b"changed" if info.filename.endswith("evidence.json") else original.read(info.filename)
            changed.writestr(info, raw)
    with pytest.raises(ValueError, match="hash mismatch"):
        release.verify_release(bad)


def validation_manifest(project, sources):
    manifest = project / release.VALIDATION_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({"source_sha256": sources}), encoding="utf-8")


def test_frozen_referenced_run_marker_preserved_exactly_unrelated_locks_excluded(project, tmp_path):
    run = project / "data/runs/baseline"
    run.mkdir(parents=True)
    marker = run / ".run.lock"
    marker.write_bytes(b"0")
    (run / "other.lock").write_bytes(b"not a dependency")
    unrelated = project / "data/runs/unrelated"
    unrelated.mkdir()
    (unrelated / ".run.lock").write_bytes(b"not a dependency")
    validation_manifest(project, {"data/runs/baseline/.run.lock": release.sha256(b"0"),
                                  "data/evidence.json": release.sha256((project / "data/evidence.json").read_bytes())})
    before = (project / release.VALIDATION_MANIFEST).read_bytes()
    archive_path = tmp_path / "validation.zip"
    release.build_release(project, archive_path)
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.read("sycophancy-confidence/data/runs/baseline/.run.lock") == b"0"
        assert archive.read("sycophancy-confidence/" + release.VALIDATION_MANIFEST) == before
        assert not any("other.lock" in name or "unrelated" in name for name in archive.namelist())
    assert (project / release.VALIDATION_MANIFEST).read_bytes() == before


@pytest.mark.parametrize("name", ["data/runs/baseline/.run.lock", "data/source.json"])
@pytest.mark.parametrize("actual", [None, b"changed"])
def test_missing_or_changed_validation_evidence_fails(project, tmp_path, name, actual):
    validation_manifest(project, {name: release.sha256(b"original")})
    if actual is not None:
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(actual)
    with pytest.raises(ValueError, match="Protected validation evidence changed, missing or excluded"):
        release.build_release(project, tmp_path / "bad.zip")


def test_referencing_an_unrelated_lock_does_not_bypass_exclusions(project, tmp_path):
    name = "data/budget.json.lock"
    (project / name).write_bytes(b"temporary")
    validation_manifest(project, {name: release.sha256(b"temporary")})
    with pytest.raises(ValueError, match="Protected validation evidence"):
        release.build_release(project, tmp_path / "bad.zip")


@pytest.mark.parametrize("name", ["../outside", "/absolute/path", "C:/absolute/path", "data\\source.json", "data/../outside", "data//source.json"])
def test_unsafe_validation_source_paths_rejected(project, tmp_path, name):
    validation_manifest(project, {name: release.sha256(b"fixture")})
    with pytest.raises(ValueError, match="Unsafe protected source path"):
        release.build_release(project, tmp_path / "bad.zip")


@pytest.mark.parametrize("name", ["data/.env", "data/key.pem"])
def test_validation_manifest_cannot_require_credential_files(project, tmp_path, name):
    validation_manifest(project, {name: release.sha256(b"fixture")})
    with pytest.raises(ValueError, match="Refusing credential material"):
        release.build_release(project, tmp_path / "bad.zip")


def test_referenced_marker_still_checked_for_secret_contents(project, tmp_path):
    path = project / "data/runs/baseline/.run.lock"
    path.parent.mkdir(parents=True)
    contents = ("sk-" + "a" * 30).encode()
    path.write_bytes(contents)
    validation_manifest(project, {"data/runs/baseline/.run.lock": release.sha256(contents)})
    with pytest.raises(ValueError, match="Possible credential in release input"):
        release.build_release(project, tmp_path / "bad.zip")


def test_technical_archive_excludes_submission_preserves_frozen_files_and_has_plain_index(project, tmp_path):
    (project / "RELEASE.md").write_text("Install and reproduce the technical files.")
    (project / "submission").mkdir()
    (project / "submission/paper.tex").write_text("Test-only article.")
    (project / "submission/presentation.pptx").write_bytes(b"Test-only deck.")
    (project / "reports").mkdir()
    (project / "reports/result.json").write_text('{"test_only":true}')
    evidence = (project / "data/evidence.json").read_bytes()
    validation_manifest(project, {"data/evidence.json": release.sha256(evidence)})
    output = tmp_path / "technical.zip"
    first = release.build_technical_release(project, output)
    second = release.build_technical_release(project, tmp_path / "same.zip")
    assert first["sha256"] == second["sha256"]
    with zipfile.ZipFile(output) as archive:
        assert not any("/submission/" in name for name in archive.namelist())
        assert archive.read("sycophancy-confidence/data/evidence.json") == evidence
        assert archive.read("sycophancy-confidence/RELEASE.md") == (project / "RELEASE.md").read_bytes()
        readme = archive.read("sycophancy-confidence/README.md").decode("utf-8")
        assert "`data/evidence.json` - " in readme
        assert readme.startswith("# Technical package")
        assert not any(0x0400 <= ord(c) <= 0x052f for c in readme)
        assert "\u2014" not in readme and "\u2013" not in readme
        assert archive.read("sycophancy-confidence/reports/result.json")


def test_technical_archive_still_refuses_modified_frozen_evidence(project, tmp_path):
    validation_manifest(project, {"data/evidence.json": release.sha256(b"before-change")})
    with pytest.raises(ValueError, match="Protected validation evidence"):
        release.build_technical_release(project, tmp_path / "bad.zip")
