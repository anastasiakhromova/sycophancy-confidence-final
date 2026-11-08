"""CSV parsing, deterministic serialization, and atomic output safety."""

from __future__ import annotations

import csv
from dataclasses import replace
import json

import pytest

from sycophancy import data
from sycophancy.constants import CLAIM_COLUMNS, PROMPT_COLUMNS
from sycophancy.data import load_claims, save_prompts, save_report
from sycophancy.prompts import generate_prompts
from sycophancy.schemas import DatasetValidationError, ValidationReport
from sycophancy.validation import validate_claims


def test_csv_round_trip_preserves_false_boolean(valid_rows, write_claim_csv):
    loaded = load_claims(write_claim_csv(valid_rows))
    assert len(loaded) == 5
    assert all(row["verified"] is False for row in loaded)
    assert len(validate_claims(loaded)[0]) == 5


@pytest.mark.parametrize("raw,expected", [("true", True), ("FALSE", False), (" True ", True), (" fAlSe ", False)])
def test_csv_boolean_parser_accepts_only_explicit_boolean_words(valid_rows, write_claim_csv, raw, expected):
    valid_rows[0]["verified"] = raw
    assert load_claims(write_claim_csv(valid_rows))[0]["verified"] is expected


@pytest.mark.parametrize("raw", ["yes", "no", "1", "0", "", "null", "falsey"])
def test_csv_invalid_boolean_never_becomes_truthy(valid_rows, write_claim_csv, raw):
    valid_rows[0]["verified"] = raw
    with pytest.raises(DatasetValidationError, match="verified"):
        validate_claims(load_claims(write_claim_csv(valid_rows)))


def test_load_accepts_utf8_bom(valid_rows, write_claim_csv):
    loaded = load_claims(write_claim_csv(valid_rows, encoding="utf-8-sig"))
    assert "claim_id" in loaded[0]
    assert len(validate_claims(loaded)[0]) == 5


def test_load_trims_header_whitespace(valid_rows, write_claim_csv):
    path = write_claim_csv(valid_rows)
    content = path.read_text(encoding="utf-8")
    header, rest = content.split("\n", 1)
    path.write_text(
        ",".join(f" {column} " for column in header.split(",")) + "\n" + rest,
        encoding="utf-8",
    )
    assert len(validate_claims(load_claims(path))[0]) == 5


@pytest.mark.parametrize("header,error_column", [
    (CLAIM_COLUMNS[:-1], "notes"),
    (CLAIM_COLUMNS + ("unexpected",), "unexpected"),
    (CLAIM_COLUMNS + ("claim_id",), "claim_id"),
    (CLAIM_COLUMNS + (" claim_id ",), "claim_id"),
])
def test_rejects_missing_duplicate_or_unknown_headers(tmp_path, header, error_column):
    path = tmp_path / "bad.csv"
    path.write_text(",".join(header) + "\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError) as exc:
        load_claims(path)
    assert error_column in str(exc.value)
    assert exc.value.report.errors


@pytest.mark.parametrize("delta", [-1, 1])
def test_rejects_rows_with_wrong_number_of_cells(tmp_path, delta):
    path = tmp_path / "bad.csv"
    cells = ["value"] * (len(CLAIM_COLUMNS) + delta)
    path.write_text(",".join(CLAIM_COLUMNS) + "\n" + ",".join(cells) + "\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError):
        load_claims(path)


@pytest.mark.parametrize("content", ["", ",".join(CLAIM_COLUMNS) + "\n"])
def test_empty_file_or_header_only_csv_is_rejected(tmp_path, content):
    path = tmp_path / "empty.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(DatasetValidationError):
        load_claims(path)


def test_unterminated_quoted_csv_is_rejected(tmp_path):
    path = tmp_path / "broken.csv"
    path.write_text(",".join(CLAIM_COLUMNS) + '\ngeo_001,geography,"The capital of Canada is Toronto.\n', encoding="utf-8")
    with pytest.raises(DatasetValidationError):
        load_claims(path)


def test_invalid_utf8_is_reported_as_validation_failure(tmp_path):
    path = tmp_path / "encoding.csv"
    path.write_bytes(b"\xff\xfe\xfa\xfb")
    with pytest.raises(DatasetValidationError) as exc:
        load_claims(path)
    assert "utf-8" in str(exc.value).lower()


def test_multiline_quoted_claim_normalizes_after_parsing(valid_rows, write_claim_csv):
    valid_rows[0]["false_claim"] = "The capital of\nCanada is Toronto."
    claims, _ = validate_claims(load_claims(write_claim_csv(valid_rows)))
    assert next(claim for claim in claims if claim.claim_id == "geo_001").false_claim == "The capital of Canada is Toronto."


def test_prompt_csv_has_exact_schema_and_lossless_multiline_prompt(claims, tmp_path):
    items = generate_prompts(claims)
    path = tmp_path / "nested" / "prompts.csv"
    save_prompts(items, path)
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == list(PROMPT_COLUMNS)
        rows = list(reader)
    assert len(rows) == len(items)
    assert all(row["verified"] == "false" for row in rows)
    assert [row["prompt"] for row in rows] == [item.prompt for item in items]
    assert [row["confidence"] for row in rows] == [item.confidence.value for item in items]


def test_report_is_json_and_serializes_all_required_fields(tmp_path):
    report = ValidationReport()
    path = tmp_path / "nested" / "report.json"
    save_report(report, path)
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert parsed == report.to_dict()
    assert set(parsed) >= {
        "total_claims", "verified_claims", "unverified_claims", "claims_per_domain",
        "duplicate_count", "missing_values", "prompt_count", "prompts_per_confidence",
        "average_prompt_length", "warnings", "errors", "validation_status",
    }


def test_saved_artifacts_are_byte_deterministic(claims, tmp_path):
    items = generate_prompts(claims)
    first, second = tmp_path / "first.csv", tmp_path / "second.csv"
    save_prompts(items, first)
    save_prompts(items, second)
    assert first.read_bytes() == second.read_bytes()
    report = ValidationReport()
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    save_report(report, first)
    save_report(report, second)
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize("artifact", ["csv", "json"])
def test_failed_atomic_replace_preserves_existing_file_and_cleans_temp(claims, tmp_path, monkeypatch, artifact):
    target = tmp_path / f"existing.{artifact}"
    target.write_bytes(b"preserve existing output")

    def fail_replace(*args, **kwargs):
        raise OSError("simulated disk replacement failure")

    monkeypatch.setattr(data.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failure"):
        if artifact == "csv":
            save_prompts(generate_prompts(claims), target)
        else:
            save_report(ValidationReport(), target)
    assert target.read_bytes() == b"preserve existing output"
    assert list(tmp_path.iterdir()) == [target]


def test_serialization_failure_preserves_existing_csv_and_cleans_temp(claims, tmp_path):
    target = tmp_path / "prompts.csv"
    target.write_bytes(b"preserve existing output")
    items = generate_prompts(claims)
    items[-1] = replace(items[-1], verified="false")
    with pytest.raises((ValueError, TypeError)):
        save_prompts(items, target)
    assert target.read_bytes() == b"preserve existing output"
    assert list(tmp_path.iterdir()) == [target]
