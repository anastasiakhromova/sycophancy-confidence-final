"""Build or verify a deterministic, allowlisted offline research ZIP (no API)."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import zipfile

PROJECT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", "RELEASE.md", "pyproject.toml", "requirements-research-lock.txt",
              ".gitignore", ".gitattributes", "LICENSE", "LICENSE.md", "CITATION.cff"}
ROOT_DIRS = {"configs", "data", "reports", "scripts", "src", "tests", "submission"}
EXCLUDED_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv",
                 "node_modules", "build", "dist", "work"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".lock", ".tmp", ".log", ".bak", ".swp",
                     ".aux", ".blg", ".fls", ".fdb_latexmk", ".nav", ".snm", ".toc"}
SECRET_SUFFIXES = {".key", ".pem", ".p12", ".pfx"}
SECRET_PATTERN = re.compile(rb"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
ARCHIVE_ROOT = "sycophancy-confidence"
INVENTORY = "RELEASE_MANIFEST.json"
VALIDATION_MANIFEST = "data/validation_v2/coordinator_manifest.json"


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def possible_credential(raw, relative):
    """Scan plaintext; random encrypted reasoning can contain an accidental sk-.

    The sole exception is an opaque provider reasoning token in the saved
    challenge response envelope. Preserve its bytes in the archive. API keys,
    ordinary text, and malformed/unencrypted values remain subject to scanning.
    This is a pattern check, not decryption or a claim of exhaustive detection.
    """
    if not SECRET_PATTERN.search(raw):
        return False
    if relative != "data/challenge_v1/run/responses.jsonl":
        return True
    try:
        rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
        for row in rows:
            for item in row.get("provider_raw_response", {}).get("output", []):
                token = item.get("encrypted_content")
                if (item.get("type") == "reasoning" and isinstance(token, str)
                        and len(token) >= 120
                        and re.fullmatch(r"gAAAAA[A-Za-z0-9_-]+={0,2}", token)):
                    item["encrypted_content"] = "[opaque encrypted reasoning token]"
        return bool(SECRET_PATTERN.search(json.dumps(rows, ensure_ascii=True).encode("utf-8")))
    except (ValueError, TypeError, AttributeError):
        return True


def protected_validation_sources(project):
    """Read the frozen dependency inventory without accepting links or unsafe paths."""
    manifest_path = project / VALIDATION_MANIFEST
    # Do not follow a linked parent while obtaining the exception inventory.
    current = project
    for part in PurePosixPath(VALIDATION_MANIFEST).parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise ValueError(f"Release input must not be a link: {current.relative_to(project).as_posix()}")
    if not manifest_path.exists():
        return {}
    payload = json.loads(manifest_path.read_bytes())
    sources = payload.get("source_sha256") if isinstance(payload, dict) else None
    if not isinstance(sources, dict):
        raise ValueError("Validation manifest must contain a source_sha256 mapping.")
    for name, expected in sources.items():
        if (not isinstance(name, str) or not name or "\\" in name or ":" in name
                or PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts
                or PurePosixPath(name).as_posix() != name):
            raise ValueError("Unsafe protected source path in validation manifest.")
        path = PurePosixPath(name)
        if any(part.lower().startswith(".env") for part in path.parts) or path.suffix.lower() in SECRET_SUFFIXES:
            raise ValueError(f"Refusing credential material in release: {name}")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"Invalid protected source hash in validation manifest: {name}")
    return sources


def collect_files(project):
    """Allow only project source, saved evidence, reports and deliverables."""
    project = Path(project).resolve()
    protected = protected_validation_sources(project)
    # Only these exact, already-frozen run markers bypass the ordinary hidden /
    # lock-file exclusions. Other locks, credentials and links remain excluded.
    required_run_markers = {
        name for name in protected
        if PurePosixPath(name).name == ".run.lock"
        and PurePosixPath(name).parts[:2] == ("data", "runs")
    }
    found = {}

    def visit(path):
        name = path.name
        relative = path.relative_to(project).as_posix()
        required_marker = relative in required_run_markers
        if name.startswith(".") and path.parent != project and not required_marker:
            return
        if name in EXCLUDED_DIRS or name.endswith(".egg-info") or name.startswith("pytest-cache-files-"):
            return
        if (path.suffix in EXCLUDED_SUFFIXES or name.endswith(("~", ".synctex.gz"))) and not required_marker:
            return
        if name.startswith(".env") or path.suffix in SECRET_SUFFIXES:
            raise ValueError(f"Refusing credential material in release: {path.relative_to(project).as_posix()}")
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise ValueError(f"Release input must not be a link: {path.relative_to(project).as_posix()}")
        if path.is_dir():
            for child in sorted(path.iterdir()):
                visit(child)
        elif path.is_file():
            raw = path.read_bytes()
            if possible_credential(raw, relative):
                raise ValueError(f"Possible credential in release input: {path.relative_to(project).as_posix()}")
            found[path.relative_to(project).as_posix()] = raw

    for name in sorted(ROOT_FILES | ROOT_DIRS):
        path = project/name
        if path.exists():
            visit(path)
    for required in ("README.md", "pyproject.toml"):
        if required not in found:
            raise ValueError(f"Missing release input: {required}")
    design_name = "data/verification/main_design.json"
    if design_name in found:
        for name, expected in json.loads(found[design_name])["files"].items():
            if name not in found or sha256(found[name]) != expected:
                raise ValueError(f"Frozen research input changed or missing: {name}")
    for name, expected in protected.items():
        if name not in found or sha256(found[name]) != expected:
            raise ValueError(f"Protected validation evidence changed, missing or excluded: {name}")
    return dict(sorted(found.items()))


def build_release(project, output):
    project, output = Path(project).resolve(), Path(output).resolve()
    if output.is_relative_to(project) and output.relative_to(project).parts[0] in ROOT_DIRS:
        raise ValueError("Release output must be outside the packaged source directories.")
    files = collect_files(project)
    return write_release(files, output)


def technical_readme(files):
    """Describe the English technical handoff without submission instructions."""
    purposes = {
        "pyproject.toml": "Project configuration and dependencies",
        "requirements-research-lock.txt": "Pinned dependency versions",
        "RELEASE.md": "Installation, reproduction and packaging",
        ".gitignore": "Git exclusions", ".gitattributes": "Preservation of original file bytes in Git",
        "confirmed_labels.jsonl": "Existing AI judgments approved by the author",
        "reported_labels.jsonl": "AI-origin reference transcribed from author-reported second-review agreement",
        "confirmation.json": "Assessment approval procedure",
        "statement.json": "Author-reported second-review procedure and outcome",
        "summary.json": "Summary results",
        "review_a.html": "Review form for 241 responses",
        "review_b.html": "Review form for 198 responses",
        "index.html": "Review packet selection",
        "claims_baseline.csv": "50 pilot claims",
        "claims_main.csv": "150 main-experiment claims",
        "responses.jsonl": "Original model responses",
        "evaluated_responses.csv": "Responses with primary automatic labels",
        "analyze_reported_review.py": "Recompute recorded-review metrics",
        "package_release.py": "Build and verify release archives",
        "reported_review_validation.py": "Validate review provenance and calculate metrics",
        "build_review_forms.py": "Build English offline review forms",
        "audit_release_language.py": "Check packaged text for remaining Cyrillic",
        "run_challenge.py": "Collect the separate 390-response controlled follow-up",
        "check_confidence_wording.py": "Collect automated ratings of nine confidence cues",
        "assess_challenge.py": "Assess follow-up responses with a blinded automated judge",
        "analyze_challenge.py": "Reproduce follow-up statistics from saved responses and judgments",
        "assessment_rubric.md": "Fixed semantic-assessment rules for the follow-up",
        "cues.json": "Three confidence cue families for the follow-up",
        "claims.jsonl": "Thirty source-referenced follow-up factual items and controls",
    }
    lines = ["# Technical package", ""]
    if "data/author_review/confirmation.json" in files:
        lines.append("The author approved 241 existing AI semantic judgments; this was not de novo independent annotation.")
    if "data/second_review/statement.json" in files:
        statement = json.loads(files["data/second_review/statement.json"])
        lines.extend(["Author-reported procedure: " + statement["statement_en"],
                      "Original second-review exports are unavailable. Item-level rows were transcribed from the author's complete-agreement summary, not independently preserved annotations.",
                      "No inter-rater reliability was measured from two original annotation sets. Metrics describe agreement with a selected AI-origin reference, not validated human accuracy.",
                      "Methods and results: reports/reviewer_validation/summary.json."])
    lines.extend(["", "## Run", "", "Python 3.11+. Saved-data analysis requires no API key.",
                  "", "```sh", "python -m pip install -r requirements-research-lock.txt",
                  "python -m pip install --no-deps --no-build-isolation -e .",
                  "python scripts/analyze_reported_review.py --figures",
                  "python scripts/analyze_challenge.py --figures", "python -m pytest", "```", "",
                  "run_experiment.py, run_main_experiment.py and run_challenge.py collect paid API responses.",
                  "check_confidence_wording.py and assess_challenge.py also make paid API requests.",
                  "", "## Files", ""])
    kinds = {"src": "Program module", "scripts": "Command-line script", "tests": "Program tests",
             "configs": "Experiment settings", "data": "Research data", "reports": "Research results"}
    for name in sorted(files):
        path = PurePosixPath(name)
        purpose = purposes.get(path.name, kinds.get(path.parts[0], "Project file"))
        if path.suffix in {".png", ".pdf"}:
            purpose = "Results figure"
        lines.append(f"- `{name}` - {purpose}.")
    lines.extend(["- `README.md` - File index and setup.",
                  "- `RELEASE_MANIFEST.json` - Per-file checksums.", ""])
    return "\n".join(lines).replace("\u2014", "-").replace("\u2013", "-").encode("utf-8")


def build_technical_release(project, output):
    """Package code, data and reports while preserving every frozen dependency."""
    project, output = Path(project).resolve(), Path(output).resolve()
    if output.is_relative_to(project) and output.relative_to(project).parts[0] in ROOT_DIRS:
        raise ValueError("Release output must be outside the packaged source directories.")
    original = collect_files(project)
    roots = {"src", "scripts", "tests", "configs", "data", "reports"}
    files = {name: raw for name, raw in original.items()
             if (PurePosixPath(name).parts[0] in roots or name in
                 {"pyproject.toml", "requirements-research-lock.txt", "RELEASE.md", ".gitignore", ".gitattributes"})
             and name not in {"reports/review_v2_preview.jpg", "reports/submission_verification.json"}}
    for name in protected_validation_sources(project):
        if name not in files:
            raise ValueError(f"Technical release would omit protected evidence: {name}")
    files["README.md"] = technical_readme(files)
    return write_release(files, output)


def write_release(files, output):
    """Write and verify one deterministic archive from an already checked inventory."""
    output = Path(output).resolve()
    manifest = {"schema_version": 1, "archive_root": ARCHIVE_ROOT,
                "license_note": "No license is granted by this packaging tool; see project licensing status.",
                "files": {name: {"bytes": len(raw), "sha256": sha256(raw)} for name, raw in files.items()}}
    files[INVENTORY] = (json.dumps(manifest, indent=2, sort_keys=True)+"\n").encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix+".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(f"{ARCHIVE_ROOT}/{name}", date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw, compresslevel=9)
    os.replace(temporary, output)
    result = verify_release(output)
    output.with_suffix(output.suffix+".sha256").write_text(f"{result['sha256']}  {output.name}\n", encoding="ascii")
    return result


def verify_release(path):
    path = Path(path)
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP entry.")
        for name in names:
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != ARCHIVE_ROOT or ".." in parts or "\\" in name:
                raise ValueError("Unsafe ZIP path.")
        manifest = json.loads(archive.read(f"{ARCHIVE_ROOT}/{INVENTORY}"))
        expected = {f"{ARCHIVE_ROOT}/{name}" for name in manifest["files"]} | {f"{ARCHIVE_ROOT}/{INVENTORY}"}
        if set(names) != expected:
            raise ValueError("ZIP inventory does not match its members.")
        for name, metadata in manifest["files"].items():
            raw = archive.read(f"{ARCHIVE_ROOT}/{name}")
            if len(raw) != metadata["bytes"] or sha256(raw) != metadata["sha256"]:
                raise ValueError(f"ZIP content hash mismatch: {name}")
    return {"archive": str(path), "files": len(manifest["files"]), "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()), "verification": "passed"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT/"work/release/sycophancy-confidence.zip")
    parser.add_argument("--verify", type=Path, metavar="ZIP")
    parser.add_argument("--technical", action="store_true", help="Include code, data and reports with a short English file index, excluding submission documents")
    args = parser.parse_args(argv)
    try:
        result = verify_release(args.verify) if args.verify else (
            build_technical_release(PROJECT, args.output) if args.technical else build_release(PROJECT, args.output))
    except (ValueError, OSError, KeyError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Release failed: {exc}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
