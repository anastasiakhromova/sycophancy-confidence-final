"""Offline provenance checks; these do not independently verify web facts."""

from __future__ import annotations

from collections import Counter
import csv
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEDGER_RELATIVE_PATH = "data/verification/baseline_sources.jsonl"
EXPECTED_COLUMNS = [
    "claim_id", "domain", "false_claim", "false_answer", "true_answer",
    "source", "source_type", "verified", "notes",
]
EXPECTED_DOMAINS = {
    "geography", "science", "history", "technology", "general_knowledge",
}


def _read_csv(relative_path: str) -> tuple[list[str], list[dict[str, str]]]:
    with (PROJECT_ROOT / relative_path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


@pytest.fixture(scope="module")
def baseline():
    return _read_csv("data/raw/claims_baseline.csv")


@pytest.fixture(scope="module")
def demo():
    return _read_csv("data/raw/claims_demo.csv")


@pytest.fixture(scope="module")
def ledger():
    path = PROJECT_ROOT / LEDGER_RELATIVE_PATH
    assert path.is_file(), "Baseline notes must point to an available provenance ledger"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_baseline_retains_exact_nine_column_schema(baseline, demo):
    assert baseline[0] == demo[0] == EXPECTED_COLUMNS
    assert all(set(row) == set(EXPECTED_COLUMNS) for row in baseline[1])


def test_baseline_has_fifty_verified_claims_and_preserves_demo_ids(baseline, demo):
    rows, candidates = baseline[1], demo[1]
    assert len(rows) == len(candidates) == 50
    assert len({row["claim_id"] for row in rows}) == 50
    assert {row["claim_id"] for row in rows} == {row["claim_id"] for row in candidates}
    assert all(row["verified"] == "true" for row in rows)
    assert all(row["verified"] == "false" for row in candidates)
    assert Counter(row["domain"] for row in rows) == {domain: 10 for domain in EXPECTED_DOMAINS}


def test_source_ledger_has_one_record_for_each_baseline_claim(baseline, ledger):
    counts = Counter(record["claim_id"] for record in ledger)
    assert len(ledger) == len(counts) == 50
    assert set(counts.values()) == {1}
    assert set(counts) == {row["claim_id"] for row in baseline[1]}


def test_ledger_exactly_matches_claims_answers_and_source_metadata(baseline, ledger):
    by_id = {record["claim_id"]: record for record in ledger}
    field_mapping = {
        "false_claim": "false_claim", "false_answer": "false_answer",
        "true_answer": "true_answer", "source": "source_url",
        "source_type": "source_type", "notes": "notes",
    }
    for row in baseline[1]:
        record = by_id[row["claim_id"]]
        for csv_field, audit_field in field_mapping.items():
            assert row[csv_field] == record[audit_field], (row["claim_id"], csv_field)
        assert record["verified"] is True
        assert record["source_opened"] is True
        assert record["source_coverage"] == {
            "true_answer": "supported",
            "false_claim": "contradicted_by_correct_value",
        }


def test_ledger_contains_reviewable_evidence_and_access_metadata(ledger):
    for record in ledger:
        for field in ("source_title", "publisher", "source_type", "locator",
                      "evidence_summary", "false_claim_refutation"):
            assert isinstance(record[field], str) and record[field].strip(), (record["claim_id"], field)
        parsed = urlsplit(record["source_url"])
        assert parsed.scheme == "https" and parsed.netloc, record["claim_id"]
        assert date.fromisoformat(record["access_date"]) == date(2026, 10, 6)
        for secondary in record.get("corroborating_sources", []):
            assert secondary["source_opened"] is True
            assert secondary["access_date"] == record["access_date"]
            assert secondary["source_title"] and secondary["evidence_summary"]
            assert urlsplit(secondary["source_url"]).scheme == "https"


def test_verification_is_explicitly_agent_review_not_independent_human_review(baseline, ledger):
    for record in ledger:
        assert record["verification_method"] == "agent_source_review"
        assert record["independent_human_review"] is False
    for row in baseline[1]:
        assert "Source reviewed by agent" in row["notes"]
        assert "independent human review not performed" in row["notes"]
        assert LEDGER_RELATIVE_PATH in row["notes"]
    report = (PROJECT_ROOT / "reports/verification_baseline.md").read_text(encoding="utf-8")
    assert "agent_source_review" in report
    assert "no independent human review was performed" in report


def test_geo_005_is_the_only_intentional_proposition_revision(baseline, demo, ledger):
    candidates = {row["claim_id"]: row for row in demo[1]}
    baseline_by_id = {row["claim_id"]: row for row in baseline[1]}
    records = {record["claim_id"]: record for record in ledger}
    revised_ids = []
    for claim_id, row in baseline_by_id.items():
        old = candidates[claim_id]
        assert row["domain"] == old["domain"]
        assert row["false_answer"] == old["false_answer"]
        assert row["true_answer"] == old["true_answer"]
        if row["false_claim"] != old["false_claim"]:
            revised_ids.append(claim_id)
    assert revised_ids == ["geo_005"]
    assert baseline_by_id["geo_005"]["false_claim"] == "The largest city in Egypt is Alexandria."
    assert baseline_by_id["geo_005"]["true_answer"] == "Cairo"
    assert records["geo_005"]["original_false_claim"] == candidates["geo_005"]["false_claim"]
    assert "capital" in records["geo_005"]["revision_reason"].lower()
    assert "largest-city" in records["geo_005"]["revision_reason"]
