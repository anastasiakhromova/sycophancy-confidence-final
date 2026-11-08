"""Synthetic fixtures for integrity checks; never empirical model responses."""
from copy import deepcopy
import hashlib
import json

import pytest

from sycophancy.diagnostics import load_ai_diagnostics, render_ai_diagnostics


@pytest.fixture
def audit(tmp_path):
    rows = [
        dict(run_id="test-run-a", response_id="test-1", model="test-a", claim_id="c1", confidence="low", label="UNCERTAIN", response="Test-only factual repair."),
        dict(run_id="test-run-a", response_id="test-2", model="test-a", claim_id="c1", confidence="high", label="UNCERTAIN", response="Test-only mixed response."),
        dict(run_id="test-run-b", response_id="test-3", model="test-b", claim_id="c1", confidence="low", label="SYCOPHANTIC", response="Test-only false endorsement."),
        dict(run_id="test-run-b", response_id="test-4", model="test-b", claim_id="c1", confidence="high", label="CORRECT", response="Test-only direct correction."),
    ]
    collection = {"evaluator_sha256": "a"*64, "aliases_sha256": "b"*64, "evaluator_version": "test-version",
                  "model_runs": [{"model": m, "specification": {"total_responses": 2}} for m in ("test-a", "test-b")]}
    cases = [{**{k: row[k] for k in ("run_id", "response_id", "model", "claim_id", "confidence")},
              "automatic_label": row["label"], "ai_assessment": assessment,
              "reason": "Synthetic test-only reason.", "evidence": row["response"],
              "response_sha256": hashlib.sha256(row["response"].encode()).hexdigest()}
             for row, assessment in zip(rows[:3], ["CORRECT", "unresolved", "SYCOPHANTIC"])]
    payload = {"audit_type": "post_hoc_ai_review", "is_human_validation": False,
               "timestamp_utc": "2026-10-06T00:00:00+00:00", **{k: collection[k] for k in ("evaluator_sha256", "aliases_sha256", "evaluator_version")},
               "scope": {"total_expected": 4, "total_available": 4, "n_non_correct": 3, "n_audited": 3, "n_correct_not_audited": 1},
               "summary": {"ai_assessment_counts": {"CORRECT": 9000}}, "cases": cases}
    path = tmp_path / "diagnostics.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path, rows, collection, payload


def save(path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_missing_optional_audit_is_omitted(tmp_path):
    assert load_ai_diagnostics(tmp_path / "missing.json", [], {}) is None
    assert load_ai_diagnostics(None, [], {}) is None
    assert render_ai_diagnostics(None) == []


def test_valid_audit_recounts_without_mutating_inputs_or_files(audit):
    path, rows, collection, payload = audit
    before = deepcopy((rows, collection))
    file_before = path.read_bytes()
    result = load_ai_diagnostics(path, rows, collection)
    assert result["summary"]["ai_assessment_counts"] == {"CORRECT": 1, "UNCERTAIN": 0, "SYCOPHANTIC": 1, "unresolved": 1}
    assert result["scope"]["automatic_label_counts"] == {"CORRECT": 1, "UNCERTAIN": 2, "SYCOPHANTIC": 1}
    assert result["summary"]["questionable_behavior_response_ids"] == ["test-2", "test-3"]
    assert (rows, collection) == before
    assert path.read_bytes() == file_before
    assert payload["summary"]["ai_assessment_counts"]["CORRECT"] == 9000


def test_render_has_correct_scope_and_ai_limitations(audit):
    path, rows, collection, _ = audit
    markdown = "\n\n".join(render_ai_diagnostics(load_ai_diagnostics(path, rows, collection)))
    for expected in ("not human validation", "not ground truth", "all 3", "among 4", "1 unresolved",
                     "| CORRECT | 1 |", "1 automatic CORRECT responses were not audited",
                     "does not estimate evaluator accuracy", "primary automatic labels and analyses remain unchanged",
                     "(evaluator_diagnostics.md)"):
        assert expected in markdown
    assert "9000" not in markdown


@pytest.mark.parametrize("field,value", [("audit_type", "human_review"), ("is_human_validation", True), ("is_human_validation", 0)])
def test_human_or_ambiguous_attribution_rejected(audit, field, value):
    path, rows, collection, payload = audit
    payload[field] = value
    save(path, payload)
    with pytest.raises(ValueError, match="audit_type|is_human_validation"):
        load_ai_diagnostics(path, rows, collection)


def test_changed_raw_response_rejected(audit):
    path, rows, collection, _ = audit
    rows[0]["response"] += " Changed after audit."
    with pytest.raises(ValueError, match="SHA256"):
        load_ai_diagnostics(path, rows, collection)


@pytest.mark.parametrize("field,value", [("run_id", "other-run"), ("response_id", "other-response"),
    ("model", "test-b"), ("claim_id", "c2"), ("confidence", "neutral"), ("automatic_label", "SYCOPHANTIC")])
def test_stale_identity_metadata_and_label_rejected(audit, field, value):
    path, rows, collection, payload = audit
    payload["cases"][0][field] = value
    save(path, payload)
    with pytest.raises(ValueError, match="stale|mismatch"):
        load_ai_diagnostics(path, rows, collection)


def test_missing_case_cannot_be_hidden_by_adjusted_scope(audit):
    path, rows, collection, payload = audit
    payload["cases"].pop()
    payload["scope"]["n_audited"] = payload["scope"]["n_non_correct"] = 2
    save(path, payload)
    with pytest.raises(ValueError, match="coverage"):
        load_ai_diagnostics(path, rows, collection)


def test_duplicate_case_cannot_replace_missing_case(audit):
    path, rows, collection, payload = audit
    payload["cases"][1] = deepcopy(payload["cases"][0])
    save(path, payload)
    with pytest.raises(ValueError, match="duplicate audit"):
        load_ai_diagnostics(path, rows, collection)


def test_duplicate_current_response_rejected(audit):
    path, rows, collection, _ = audit
    rows[1] = deepcopy(rows[0])
    with pytest.raises(ValueError, match="duplicate current"):
        load_ai_diagnostics(path, rows, collection)


def test_new_non_correct_label_requires_new_audit(audit):
    path, rows, collection, _ = audit
    rows[3]["label"] = "UNCERTAIN"
    with pytest.raises(ValueError, match="coverage"):
        load_ai_diagnostics(path, rows, collection)


def test_incomplete_current_collection_rejected(audit):
    path, rows, collection, _ = audit
    with pytest.raises(ValueError, match="complete collection"):
        load_ai_diagnostics(path, rows[:-1], collection)


@pytest.mark.parametrize("field", ["evaluator_sha256", "aliases_sha256"])
def test_frozen_hash_mismatch_rejected(audit, field):
    path, rows, collection, payload = audit
    payload[field] = "c"*64
    save(path, payload)
    with pytest.raises(ValueError, match=field):
        load_ai_diagnostics(path, rows, collection)


def test_nonverbatim_evidence_rejected(audit):
    path, rows, collection, payload = audit
    payload["cases"][0]["evidence"] = "Not in the actual response."
    save(path, payload)
    with pytest.raises(ValueError, match="verbatim"):
        load_ai_diagnostics(path, rows, collection)


@pytest.mark.parametrize("field", ["total_expected", "total_available", "n_non_correct", "n_audited", "n_correct_not_audited"])
def test_wrong_scope_totals_rejected(audit, field):
    path, rows, collection, payload = audit
    payload["scope"][field] += 1
    save(path, payload)
    with pytest.raises(ValueError, match=field):
        load_ai_diagnostics(path, rows, collection)


def test_supplied_scope_label_counts_are_recomputed(audit):
    path, rows, collection, payload = audit
    payload["scope"]["automatic_label_counts"] = {"CORRECT": 4}
    payload["scope"]["automatic_label_counts_by_model"] = {"invented": {"CORRECT": 100}}
    save(path, payload)
    result = load_ai_diagnostics(path, rows, collection)
    assert result["scope"]["automatic_label_counts"]["UNCERTAIN"] == 2
    assert set(result["scope"]["automatic_label_counts_by_model"]) == {"test-a", "test-b"}


def test_invalid_json_rejected(audit):
    path, rows, collection, _ = audit
    path.write_text("{invalid", encoding="utf-8")
    with pytest.raises(ValueError, match="valid JSON"):
        load_ai_diagnostics(path, rows, collection)
