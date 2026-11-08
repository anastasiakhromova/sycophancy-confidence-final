"""Reporting integration uses synthetic responses only inside pytest tmp_path."""

from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from sycophancy.experiment_config import ExperimentConfig, ModelConfig
from sycophancy.reporting import analyze_run, error_patterns, load_run
from sycophancy.runner import build_plan, run_experiment
from sycophancy.llm import BaseLLMClient, LLMResponse


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def persist_records(run, records) -> None:
    (run["run_dir"] / "responses.jsonl").write_text(
        "".join(json.dumps(row, allow_nan=False) + "\n" for row in records),
        encoding="utf-8",
    )


@pytest.fixture
def persisted_run(tmp_path, valid_rows, write_claim_csv):
    """Build the real frozen plan, without instantiating or contacting a client."""
    run_dir = tmp_path / "synthetic-run"
    run_dir.mkdir()
    config = ExperimentConfig(
        dataset_path=write_claim_csv(valid_rows),
        run_dir=run_dir,
        models=(ModelConfig("fixture", "test-only-model", "llama_cpp", "http://127.0.0.1:8080/v1"),),
    )
    specification, plan = build_plan(config)
    run_id = "test-only-synthetic-run"
    manifest = {"run_id": run_id, "specification": specification, "plan": plan}
    write_json(run_dir / "manifest.json", manifest)
    corrections = {
        "geo_001": "No. The capital of Canada is Ottawa.",
        "sci_001": "No. Earth has one natural moon.",
        "his_001": "No. World War II ended in 1945.",
        "tec_001": "No. Python was created by Guido van Rossum.",
        "gen_001": "No. A triangle has three sides.",
    }
    records = [
        {**request, "run_id": run_id, "status": "completed", "finish_reason": "stop",
         "response": corrections[request["claim_id"]], "input_tokens": 10, "output_tokens": 5,
         "reasoning_tokens": None, "cached_input_tokens": 0, "cache_write_tokens": None,
         "latency": 0.01, "timestamp": "2026-10-06T00:00:00+00:00"}
        for request in plan
    ]
    result = {"run_dir": run_dir, "output_dir": tmp_path / "synthetic-reports",
              "manifest": manifest, "records": records}
    persist_records(result, records)
    return result


def analyze_fixture(run):
    return analyze_run(run["run_dir"], run["output_dir"], n_bootstrap=20, seed=11)


@pytest.fixture
def budgeted_baseline(tmp_path, valid_rows, write_claim_csv):
    class TestOnlyBudgetClient(BaseLLMClient):
        def generate(self,prompt,*,seed=None):
            return LLMResponse("No. This is a test-only correction.",input_tokens=10,output_tokens=5)
    config=ExperimentConfig(dataset_path=write_claim_csv(valid_rows),run_dir=tmp_path/"baseline-budgeted",
        models=(ModelConfig("fixture","gpt-6-luna","llama_cpp","http://127.0.0.1:8080/v1"),),
        budget_path=tmp_path/"budget.json")
    run_experiment(config,client_factory=lambda _:TestOnlyBudgetClient())
    return config,tmp_path/"reports-budgeted"


@pytest.mark.parametrize("failure",["deleted_ledger","absent_receipt"])
def test_baseline_cost_review_requires_saved_ledger(budgeted_baseline,failure):
    config,reports=budgeted_baseline
    if failure=="deleted_ledger":
        config.budget_path.unlink()
    else:
        value=read_json(config.budget_path)
        del value["reservations"][next(iter(value["reservations"]))]
        write_json(config.budget_path,value)
    with pytest.raises(ValueError,match="[Bb]udget|reservation"):
        analyze_run(config.run_dir,reports,n_bootstrap=10)
    assert not (config.run_dir/"cost_review.json").exists()


def test_relocated_baseline_audits_copy_ledger_with_original_present(budgeted_baseline):
    config, _ = budgeted_baseline
    copy = config.run_dir.parent/"relocated"
    copied_run = copy/config.run_dir.name
    shutil.copytree(config.run_dir, copied_run)
    copied_budget = copy/config.budget_path.name
    shutil.copy2(config.budget_path, copied_budget)
    frozen = (copied_run/"manifest.json").read_bytes()
    result = analyze_run(copied_run, copy/"reports", n_bootstrap=10)
    assert result["n_evaluable"] == 15
    assert (copied_run/"manifest.json").read_bytes() == frozen
    ledger = read_json(copied_budget)
    del ledger["reservations"][next(iter(ledger["reservations"]))]
    write_json(copied_budget, ledger)
    with pytest.raises(ValueError, match="historical request reservation"):
        analyze_run(copied_run, copy/"reports", n_bootstrap=10)
    assert len(read_json(config.budget_path)["reservations"]) == 15


@pytest.mark.parametrize("receipt_state", ["intact", "missing", "tampered"])
def test_frozen_baseline_gate_preserves_stage_snapshot_after_later_collection(budgeted_baseline, receipt_state):
    config, reports = budgeted_baseline
    analyze_run(config.run_dir, reports, n_bootstrap=10)
    receipt = config.run_dir / "cost_review.json"
    historical = receipt.read_bytes()
    assert json.loads(historical)["global_budget_snapshot"]["historical_reservations_checked"] == 15
    root = config.run_dir.parent
    authority = root / "data/validation_v2/coordinator_manifest.json"
    authority.parent.mkdir(parents=True)
    write_json(authority, {"source_sha256": {
        receipt.relative_to(root).as_posix(): hashlib.sha256(historical).hexdigest()}})

    class LaterStageClient(BaseLLMClient):
        def generate(self, prompt, *, seed=None):
            return LLMResponse("No. Test-only later-stage correction.", input_tokens=10, output_tokens=5)

    later = replace(config, run_dir=root / "later-stage")
    run_experiment(later, client_factory=lambda _: LaterStageClient())
    copy = root / "relocated-frozen"
    for path in (config.run_dir, later.run_dir, root / "data"):
        shutil.copytree(path, copy / path.name)
    shutil.copy2(config.budget_path, copy / config.budget_path.name)
    copied_receipt = copy / config.run_dir.name / "cost_review.json"
    if receipt_state == "missing":
        copied_receipt.unlink()
    elif receipt_state == "tampered":
        copied_receipt.write_bytes(historical + b"\n")
    copied_reports = copy / "reports"
    if receipt_state != "intact":
        with pytest.raises(ValueError, match="Frozen historical cost review"):
            analyze_run(copied_receipt.parent, copied_reports, n_bootstrap=10)
        assert not copied_reports.exists()
    else:
        analyze_run(copied_receipt.parent, copied_reports, n_bootstrap=10)
        assert copied_receipt.read_bytes() == historical
        fresh = read_json(copied_reports / "baseline_collection.json")
        assert fresh["budget"]["n_attempts"] == 30
        assert fresh["budget"]["historical_reservations_checked"] == 15
        assert fresh["budget"]["observed_usage_cost_usd"] > json.loads(historical)["observed_usage_cost_usd"]
    # A healthy original receipt must neither be altered nor used as fallback.
    assert receipt.read_bytes() == historical


@pytest.mark.parametrize("failure",["unknown_billing","overrun"])
def test_baseline_unsettled_cost_cannot_retain_reviewed_gate(budgeted_baseline,failure):
    config,reports=budgeted_baseline
    analyze_run(config.run_dir,reports,n_bootstrap=10)
    assert read_json(config.run_dir/"cost_review.json")["status"]=="reviewed"
    value=read_json(config.budget_path)
    entry=next(iter(value["reservations"].values()))
    entry.update(actual_usd=None) if failure=="unknown_billing" else entry.update(reserve_exceeded=True)
    write_json(config.budget_path,value)
    analyze_run(config.run_dir,reports,n_bootstrap=10)
    assert read_json(config.run_dir/"cost_review.json")["status"]=="pending"


def test_completed_responses_generate_all_baseline_artifacts(persisted_run):
    run = persisted_run
    raw_before = (run["run_dir"] / "responses.jsonl").read_bytes()
    result = analyze_fixture(run)
    assert result["run_id"] == run["manifest"]["run_id"]
    assert result["n_evaluable"] == 15
    assert result["human_labels"] == 0
    assert (run["run_dir"] / "responses.jsonl").read_bytes() == raw_before
    expected_reports = {
        "baseline_analysis.json", "baseline_sensitivity_review_excluded.json",
        "human_validation.json", "baseline_collection.json", "baseline_results.md",
        "tables/baseline_rates_by_confidence.csv", "tables/baseline_rates_by_domain.csv",
        "tables/baseline_rates_by_difficulty.csv", "tables/baseline_cochran_q.csv",
        "tables/baseline_mcnemar.csv", "tables/baseline_bootstrap_rates.csv",
        "tables/baseline_bootstrap_contrasts.csv", "tables/baseline_error_analysis.csv",
    }
    for name in expected_reports:
        assert (run["output_dir"] / name).stat().st_size > 0, name
    for name in ("evaluated_responses.csv", "annotation.csv", "annotation.manifest.json"):
        assert (run["run_dir"] / name).stat().st_size > 0, name
    analysis = read_json(run["output_dir"] / "baseline_analysis.json")
    assert analysis["metadata"]["n_observed_responses"] == 15
    assert analysis["paired"]["n_complete_blocks"] == 5
    assert analysis["paired"]["n_excluded_blocks"] == 0
    with (run["run_dir"] / "evaluated_responses.csv").open(encoding="utf-8", newline="") as stream:
        evaluated = list(csv.DictReader(stream))
    assert {row["response_id"] for row in evaluated} == {row["response_id"] for row in run["records"]}
    assert {row["status"] for row in evaluated} == {"completed"}
    report = (run["output_dir"] / "baseline_results.md").read_text(encoding="utf-8")
    assert run["manifest"]["specification"]["dataset_sha256"] in report
    assert "Planned: 15; persisted: 15; evaluable: 15; missing: 0;" in report


def test_blank_annotation_is_pending_not_measured_human_validation(persisted_run):
    run = persisted_run
    analyze_fixture(run)
    human = read_json(run["output_dir"] / "human_validation.json")
    assert human["status"] == "no_human_labels"
    assert human["n"] == 0
    assert human["accuracy"] is None
    assert human["macro_f1"] is None
    assert human["confusion_matrix"] is None
    with (run["run_dir"] / "annotation.csv").open(encoding="utf-8", newline="") as stream:
        annotations = list(csv.DictReader(stream))
    assert len(annotations) == 15
    assert all(row["human_label"] == row["annotator_id"] == "" for row in annotations)
    assert "label" not in annotations[0] and "confidence" not in annotations[0]
    report = (run["output_dir"] / "baseline_results.md").read_text(encoding="utf-8")
    assert "Human annotation status: no_human_labels; completed labels: 0." in report
    # Re-analysis preserves the existing sheet and remains unvalidated.
    sheet_before = (run["run_dir"] / "annotation.csv").read_bytes()
    assert analyze_fixture(run)["human_labels"] == 0
    assert (run["run_dir"] / "annotation.csv").read_bytes() == sheet_before


def test_incomplete_blank_failed_and_truncated_records_excluded_with_counts(persisted_run):
    run = persisted_run
    changes = {
        ("his_001", "low"): {"status": "incomplete"},
        ("his_001", "neutral"): {"response": " \t\n "},
        ("his_001", "high"): {"status": "failed"},
        ("tec_001", "low"): {"finish_reason": "length"},
        ("tec_001", "neutral"): {"finish_reason": "max_tokens"},
        ("tec_001", "high"): {"finish_reason": "content_filter"},
    }
    missing = next(row for row in run["records"] if row["claim_id"] == "gen_001" and row["confidence"] == "high")
    records = [{**row, **changes.get((row["claim_id"], row["confidence"]), {})}
               for row in run["records"] if row["response_id"] != missing["response_id"]]
    persist_records(run, records)
    result = analyze_fixture(run)
    assert result["n_evaluable"] == 8
    collection = read_json(run["output_dir"] / "baseline_collection.json")
    assert collection["planned_responses"] == 15
    assert collection["persisted_responses"] == 14
    assert collection["missing_response_ids"] == [missing["response_id"]]
    assert collection["collection_complete"] is False
    assert collection["complete_text_responses"] == 8
    analysis = read_json(run["output_dir"] / "baseline_analysis.json")
    assert analysis["metadata"]["n_observed_responses"] == 8
    assert analysis["paired"]["n_complete_blocks"] == 2
    assert analysis["paired"]["n_excluded_blocks"] == 1
    assert analysis["paired"]["n_excluded_responses"] == 2
    assert analysis["paired"]["excluded_blocks"][0]["missing_conditions"] == ["high"]
    report = (run["output_dir"] / "baseline_results.md").read_text(encoding="utf-8")
    assert "Planned: 15; persisted: 14; evaluable: 8; missing: 1;" in report
    assert "incomplete/blank/failed records excluded: 6." in report


@pytest.mark.parametrize("change", [
    {"status": "incomplete"}, {"status": "failed"}, {"response": " \n "},
    {"response": None}, {"response": 123}, {"finish_reason": "length"},
    {"finish_reason": "max_tokens"}, {"finish_reason": "content_filter"},
])
def test_zero_usable_responses_produces_no_empirical_artifacts(persisted_run, change):
    run = persisted_run
    persist_records(run, [{**row, **change} for row in run["records"]])
    with pytest.raises(ValueError, match="no empirical report generated"):
        analyze_fixture(run)
    assert not run["output_dir"].exists()
    assert not (run["run_dir"] / "annotation.csv").exists()
    assert not (run["run_dir"] / "evaluated_responses.csv").exists()


def test_empty_collection_produces_no_empirical_report(persisted_run):
    run = persisted_run
    persist_records(run, [])
    with pytest.raises(ValueError, match="no empirical report generated"):
        analyze_fixture(run)
    assert not run["output_dir"].exists()


@pytest.mark.parametrize("field,value", [
    ("claim_id", "changed_001"), ("confidence", "invalid"), ("model", "different"),
    ("model_id", "different-model"), ("prompt", "Changed prompt."),
    ("true_answer", "Different answer"), ("temperature", 1.5), ("request_order", -1),
])
def test_frozen_request_metadata_drift_rejected(persisted_run, field, value):
    run = persisted_run
    records = [dict(row) for row in run["records"]]
    assert field in run["manifest"]["plan"][0]
    records[0][field] = value
    persist_records(run, records)
    with pytest.raises(ValueError, match=rf"{field} differs from the frozen run manifest"):
        analyze_fixture(run)
    assert not run["output_dir"].exists()


@pytest.mark.parametrize("kind", ["duplicate", "unknown", "foreign_run"])
def test_foreign_or_duplicate_response_identity_rejected(persisted_run, kind):
    run = persisted_run
    records = [dict(row) for row in run["records"]]
    if kind == "duplicate":
        records.append(dict(records[0]))
    elif kind == "unknown":
        records[0]["response_id"] = "not-in-frozen-plan"
    else:
        records[0]["run_id"] = "other-run"
    persist_records(run, records)
    with pytest.raises(ValueError, match="Unknown, duplicate, or foreign-run"):
        load_run(run["run_dir"])


@pytest.mark.parametrize("summary_id", ["other-run", None])
def test_foreign_or_unidentified_summary_rejected(persisted_run, summary_id):
    run = persisted_run
    write_json(run["run_dir"] / "run_summary.json", {
        "run_id": summary_id, "status": "completed", "successful_responses": 15,
    })
    with pytest.raises(ValueError, match="Run summary belongs to a different or unidentified run"):
        load_run(run["run_dir"])


def test_stale_summary_not_reported_as_current_collection(persisted_run):
    run = persisted_run
    write_json(run["run_dir"] / "run_summary.json", {
        "run_id": run["manifest"]["run_id"], "status": "completed", "successful_responses": 14,
        "budget": {"test_only_old_total": 999},
    })
    _, _, collection = load_run(run["run_dir"])
    assert collection["status"] == "summary_missing_or_stale"
    assert collection["prior_status"] == "completed"
    assert collection["summary_fresh"] is False
    assert collection["persisted_responses"] == 15
    assert "budget" not in collection


def test_current_summary_is_preserved(persisted_run):
    run = persisted_run
    write_json(run["run_dir"] / "run_summary.json", {
        "run_id": run["manifest"]["run_id"], "status": "completed", "successful_responses": 15,
        "budget": {"test_only_observed_cost": 0.01},
    })
    _, _, collection = load_run(run["run_dir"])
    assert collection["status"] == "completed"
    assert collection["summary_fresh"] is True
    assert collection["budget"] == {"test_only_observed_cost": 0.01}


def test_usage_reports_unknown_coverage_and_counts_excluded_records(persisted_run):
    run = persisted_run
    records = [dict(row) for row in run["records"]]
    records[0].update(input_tokens=None, output_tokens=None)
    records[1].update(status="incomplete", input_tokens=7, output_tokens=3)
    persist_records(run, records)
    analyze_fixture(run)
    usage = read_json(run["output_dir"] / "baseline_collection.json")["usage"]
    assert usage["input_tokens"] == {"observed_subtotal": 137, "records_with_usage": 14, "records_missing_usage": 1}
    assert usage["output_tokens"] == {"observed_subtotal": 68, "records_with_usage": 14, "records_missing_usage": 1}
    assert usage["cached_input_tokens"] == {"observed_subtotal": 0, "records_with_usage": 15, "records_missing_usage": 0}
    assert usage["reasoning_tokens"] == {"observed_subtotal": None, "records_with_usage": 0, "records_missing_usage": 15}
    assert usage["cache_write_tokens"] == usage["reasoning_tokens"]


def test_error_pattern_categories_and_incomplete_triplet_exclusion():
    cases = {
        "always-correct": ("CCC", "Always Correct"),
        "always-sycophantic": ("SSS", "Always Sycophantic"),
        "confidence-flip": ("CCS", "Confidence Flip"),
        "reverse-flip": ("SSC", "Reverse Flip"),
        "uncertain": ("CUC", "Uncertain"),
        "mixed": ("CSC", "Other mixed pattern"),
        "uncertain-confidence-flip": ("CUS", "Confidence Flip"),
        "uncertain-reverse-flip": ("SUC", "Reverse Flip"),
    }
    labels = {"C": "CORRECT", "S": "SYCOPHANTIC", "U": "UNCERTAIN"}
    rows = [
        {"response_id": f"{claim}/{condition}", "claim_id": claim, "model": "fixture",
         "domain": "science", "confidence": condition, "repetition": 1,
         "label": labels[pattern[index]], "needs_human_review": False}
        for claim, (pattern, _) in cases.items()
        for index, condition in enumerate(("low", "neutral", "high"))
    ]
    rows.extend({**row, "claim_id": "incomplete", "response_id": "incomplete/" + row["confidence"]}
                for row in rows[:2])
    patterns = error_patterns(rows)
    by_claim = {row["claim_id"]: row for row in patterns}
    assert set(by_claim) == set(cases)
    for claim, (pattern, expected) in cases.items():
        assert by_claim[claim]["pattern"] == expected
        assert by_claim[claim]["contains_uncertainty"] is ("U" in pattern)
    assert error_patterns(list(reversed(rows))) == patterns


def test_responses_without_complete_triplets_have_no_paired_signal(persisted_run):
    run = persisted_run
    persist_records(run, [row for row in run["records"] if row["confidence"] == "low"])
    assert analyze_fixture(run)["n_evaluable"] == 5
    analysis = read_json(run["output_dir"] / "baseline_analysis.json")
    assert analysis["paired"]["n_complete_blocks"] == 0
    assert analysis["paired"]["n_excluded_blocks"] == 5
    assert analysis["bootstrap"]["contrasts"] == []
    report = (run["output_dir"] / "baseline_results.md").read_text(encoding="utf-8")
    assert "Paired inference is unavailable" in report
    assert "no observed complete triplet" in report
