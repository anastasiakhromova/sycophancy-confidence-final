"""Run the offline pipeline and check its public artifacts and failure behavior."""

from __future__ import annotations

import csv
import json
from pathlib import Path
import subprocess
import sys

from sycophancy.cli import main


def test_cli_success_creates_csv_and_passed_report(valid_rows, write_claim_csv, tmp_path, capsys):
    source = write_claim_csv(valid_rows)
    output = tmp_path / "processed" / "prompts.csv"
    report = tmp_path / "validation" / "report.json"
    assert main(["--input", str(source), "--output", str(output), "--report", str(report)]) == 0
    with output.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 15
    parsed = json.loads(report.read_text(encoding="utf-8"))
    assert parsed["total_claims"] == 5
    assert parsed["prompt_count"] == 15
    assert parsed["validation_status"].lower() == "passed"
    assert parsed["errors"] == []
    captured = capsys.readouterr()
    assert "15" in captured.out + captured.err


def test_cli_repeated_runs_are_byte_identical(valid_rows, write_claim_csv, tmp_path):
    source = write_claim_csv(valid_rows)
    output = tmp_path / "prompts.csv"
    report = tmp_path / "report.json"
    arguments = ["--input", str(source), "--output", str(output), "--report", str(report)]
    assert main(arguments) == 0
    first = output.read_bytes(), report.read_bytes()
    assert main(arguments) == 0
    assert (output.read_bytes(), report.read_bytes()) == first


def test_cli_reordered_input_has_identical_output_and_report(valid_rows, write_claim_csv, tmp_path):
    paths = [write_claim_csv(valid_rows, "first.csv"), write_claim_csv(list(reversed(valid_rows)), "second.csv")]
    artifacts = []
    for index, source in enumerate(paths):
        output, report = tmp_path / f"prompts{index}.csv", tmp_path / f"report{index}.json"
        assert main(["--input", str(source), "--output", str(output), "--report", str(report)]) == 0
        artifacts.append((output.read_bytes(), report.read_bytes()))
    assert artifacts[0] == artifacts[1]


def test_cli_invalid_dataset_preserves_previous_output_and_writes_failed_report(valid_rows, write_claim_csv, tmp_path):
    valid_rows[0]["true_answer"] = ""
    source = write_claim_csv(valid_rows)
    output, report = tmp_path / "prompts.csv", tmp_path / "report.json"
    output.write_text("previous successful prompts", encoding="utf-8")
    report.write_text('{"validation_status": "PASSED"}', encoding="utf-8")
    assert main(["--input", str(source), "--output", str(output), "--report", str(report)]) == 1
    assert output.read_text(encoding="utf-8") == "previous successful prompts"
    parsed = json.loads(report.read_text(encoding="utf-8"))
    assert parsed["validation_status"].lower() == "failed"
    assert any("true_answer" in error for error in parsed["errors"])


def test_require_verified_rejects_demo_and_does_not_write_processed_file(valid_rows, write_claim_csv, tmp_path):
    source = write_claim_csv(valid_rows)
    output, report = tmp_path / "prompts.csv", tmp_path / "report.json"
    assert main(["--input", str(source), "--output", str(output), "--report", str(report), "--require-verified"]) == 1
    assert not output.exists()
    parsed = json.loads(report.read_text(encoding="utf-8"))
    assert parsed["validation_status"].lower() == "failed"
    assert any("verified" in error.lower() for error in parsed["errors"])


def test_require_verified_accepts_complete_provenance(valid_rows, write_claim_csv, tmp_path):
    for row in valid_rows:
        row.update(verified=True, source="Synthetic test bibliography", source_type="book")
    source = write_claim_csv(valid_rows)
    output, report = tmp_path / "prompts.csv", tmp_path / "report.json"
    assert main(["--input", str(source), "--output", str(output), "--report", str(report), "--require-verified"]) == 0
    parsed = json.loads(report.read_text(encoding="utf-8"))
    assert parsed["verified_claims"] == 5
    assert parsed["unverified_claims"] == 0


def test_missing_input_is_a_clean_cli_failure(tmp_path):
    source = tmp_path / "missing.csv"
    output, report = tmp_path / "prompts.csv", tmp_path / "report.json"
    assert main(["--input", str(source), "--output", str(output), "--report", str(report)]) == 1
    assert not output.exists()
    parsed = json.loads(report.read_text(encoding="utf-8"))
    assert parsed["validation_status"].lower() == "failed"
    assert parsed["errors"]


def test_cli_refuses_to_overwrite_input_with_output(valid_rows, write_claim_csv, tmp_path):
    source = write_claim_csv(valid_rows)
    original = source.read_bytes()
    assert main(["--input", str(source), "--output", str(source), "--report", str(tmp_path / "report.json")]) == 1
    assert source.read_bytes() == original


def test_cli_refuses_output_report_path_collision(valid_rows, write_claim_csv, tmp_path):
    source = write_claim_csv(valid_rows)
    output = tmp_path / "result.csv"
    assert main(["--input", str(source), "--output", str(output), "--report", str(output)]) == 1
    assert not output.exists()


def test_script_entrypoint_runs_from_unrelated_working_directory(valid_rows, write_claim_csv, tmp_path):
    source = write_claim_csv(valid_rows)
    output, report = tmp_path / "prompts.csv", tmp_path / "report.json"
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, str(project / "scripts" / "prepare_dataset.py"),
         "--input", str(source), "--output", str(output), "--report", str(report)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert output.is_file()
    assert json.loads(report.read_text(encoding="utf-8"))["prompt_count"] == 15


def test_committed_demo_is_balanced_candidate_data():
    project = Path(__file__).resolve().parents[1]
    with (project / "data" / "raw" / "claims_demo.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    counts = {domain: sum(row["domain"] == domain for row in rows) for domain in [
        "geography", "science", "history", "technology", "general_knowledge",
    ]}
    assert len(rows) >= 25
    assert all(count >= 5 for count in counts.values())
    assert max(counts.values()) - min(counts.values()) <= 1
    assert all(row["verified"].strip().lower() == "false" for row in rows)
    assert all(not row["source"].strip() for row in rows)
