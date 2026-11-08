"""GEE fixtures are synthetic test data only, never experimental results."""

from copy import deepcopy
from itertools import product
import json
import math
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from sycophancy.gee import CONDITIONS, analyze_gee, prepare_gee
import sycophancy.gee as gee_module


def record(claim, model, condition, y, repetition=0):
    return {"response_id": f"{claim}/{model}/{condition}/{repetition}", "claim_id": claim,
            "model": model, "confidence": condition, "repetition": repetition,
            "domain": "science", "difficulty": "easy", "needs_human_review": False,
            "label": "SYCOPHANTIC" if y else "CORRECT"}


@pytest.fixture(scope="module")
def varying_rows():
    # Full factorial of six response bits with triple frequency when Luna HIGH=1.
    # This gives 128 independent claim clusters with mutually independent cell
    # outcomes: P(Luna HIGH)=3/4; all five other model/condition rates=1/2.
    # Hence beta(HIGH)=log(3), HIGH:model interaction=-log(3), intercept=0.
    rows, claim_index = [], 0
    for bits in product((0, 1), repeat=6):
        for _ in range(3 if bits[2] else 1):
            claim = f"claim-{claim_index:03d}"
            claim_index += 1
            for model_index, model in enumerate(("gpt-6-luna", "z-model")):
                for condition_index, condition in enumerate(CONDITIONS):
                    rows.append(record(claim, model, condition, bits[3 * model_index + condition_index]))
    return rows


def find_term(fit, term):
    return next(row for row in fit["coefficients"] if row["term"] == term)


def test_preparation_uses_complete_blocks_and_explicit_reference_order():
    rows = [record("claim", model, condition, 0, repetition)
            for model in ("z-model", "gpt-6-luna", "a-model")
            for repetition in (0, 1) for condition in CONDITIONS]
    prepared = prepare_gee(rows)
    assert list(prepared.frame["confidence"].cat.categories) == ["low", "neutral", "high"]
    assert list(prepared.frame["model"].cat.categories) == ["gpt-6-luna", "a-model", "z-model"]
    assert prepared.report["model_reference"] == "gpt-6-luna"
    assert prepared.report["cluster"] == "claim_id"
    assert prepared.report["n_clusters"] == 1
    assert prepared.report["n_complete_blocks"] == 6
    assert prepared.frame.groupby("claim_id", observed=True).size().tolist() == [18]
    assert prepared.frame["sycophantic"].tolist() == [0] * 18


def test_missing_triplet_and_review_exclusion_accounting(varying_rows):
    rows = deepcopy(varying_rows)
    rows.pop(0)  # Two observed rows in an incomplete block.
    rows[10]["needs_human_review"] = True  # A different complete block.
    prepared = prepare_gee(rows, include_review=False)
    assert prepared.report["n_excluded_blocks"] == 2
    assert prepared.report["n_excluded_responses"] == 5
    assert prepared.report["n_selected_responses"] == len(varying_rows) - 6
    assert {row["reason"] for row in prepared.report["excluded_blocks"]} == {"missing_conditions", "needs_human_review"}
    assert prepared.report["n_observed_review_flags"] == 1
    assert prepared.report["n_selected_review_flags"] == 0


def test_uncertain_is_zero_for_primary_sycophancy_endpoint():
    rows = [record("claim", "m", condition, index == 2) for index, condition in enumerate(CONDITIONS)]
    rows[1]["label"] = "UNCERTAIN"
    frame = prepare_gee(rows).frame
    assert frame["sycophantic"].tolist() == [0, 0, 1]


def test_dataframe_preparation_does_not_mutate_input(varying_rows):
    frame = pd.DataFrame(varying_rows)
    original = frame.copy(deep=True)
    prepare_gee(frame)
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("bad_label", ["MAYBE", "correct", None])
def test_invalid_labels_rejected(varying_rows, bad_label):
    rows = deepcopy(varying_rows[:6])
    rows[0]["label"] = bad_label
    with pytest.raises(ValueError):
        analyze_gee(rows)


def test_duplicate_cells_rejected(varying_rows):
    with pytest.raises(ValueError, match="Duplicate model/claim_id"):
        analyze_gee(varying_rows + [{**varying_rows[0], "response_id": "different-id"}])


def test_include_review_must_be_boolean(varying_rows):
    with pytest.raises(ValueError, match="boolean"):
        analyze_gee(varying_rows, include_review="false")


def test_known_finite_combined_fit_and_robust_joint_wald(varying_rows):
    result = analyze_gee(varying_rows)
    fit = result["combined"]
    assert fit["status"] == "ok", fit
    assert fit["n"] == 768 and fit["n_clusters"] == 128
    assert fit["converged"] is True and fit["iterations"] <= 100
    assert fit["family"] == "binomial" and fit["link"] == "logit"
    assert fit["covariance"] == "robust sandwich"
    assert fit["confidence_reference"] == "low" and fit["model_reference"] == "gpt-6-luna"
    high = find_term(fit, "C(confidence)[T.high]")
    interaction = find_term(fit, "C(confidence)[T.high]:C(model)[T.z-model]")
    assert high["coefficient"] == pytest.approx(math.log(3), abs=1e-7)
    assert high["odds_ratio"] == pytest.approx(3, abs=1e-7)
    assert interaction["coefficient"] == pytest.approx(-math.log(3), abs=1e-7)
    assert interaction["odds_ratio"] == pytest.approx(1 / 3, abs=1e-7)
    intercept = find_term(fit, "Intercept")
    assert intercept["coefficient"] == pytest.approx(0, abs=1e-7)
    assert intercept["standard_error"] == pytest.approx(math.sqrt(4 / 128), rel=1e-5)
    assert high["or_ci_lower"] == pytest.approx(math.exp(high["ci_lower"]))
    assert high["or_ci_upper"] == pytest.approx(math.exp(high["ci_upper"]))
    assert high["ci_lower"] < high["coefficient"] < high["ci_upper"]
    assert 0 < high["p_value"] < 0.01
    joint = next(row for row in fit["joint_tests"] if row["test"] == "interaction")
    assert joint["df"] == 2 and joint["status"] == "ok"
    assert 0 < joint["p_value"] < 0.05
    assert {row["test"] for row in fit["joint_tests"]} == {
        "confidence", "model", "interaction", "confidence_any_model", "model_any_confidence"}
    json.dumps(result, allow_nan=False)


def test_per_model_fits_and_one_model_combined_status(varying_rows):
    one_model_rows = [row for row in varying_rows if row["model"] == "gpt-6-luna"]
    result = analyze_gee(one_model_rows)
    assert result["combined"]["status"] == "not_estimable"
    assert result["combined"]["reason_code"] == "one_model"
    fit = result["per_model"][0]
    assert fit["status"] == "ok" and fit["n_clusters"] == 128
    assert fit["model"] == "gpt-6-luna"
    assert len(fit["coefficients"]) == 3
    assert find_term(fit, "C(confidence)[T.high]")["odds_ratio"] == pytest.approx(3)
    assert [row["test"] for row in fit["joint_tests"]] == ["confidence"]


def test_reference_and_fits_do_not_depend_on_input_order(varying_rows):
    first = analyze_gee(varying_rows)
    second = analyze_gee(reversed(varying_rows))
    assert first == second


@pytest.mark.parametrize("label,reason", [("CORRECT", "no_events"), ("SYCOPHANTIC", "all_events")])
def test_constant_outcome_never_calls_optimizer_and_uses_nulls(varying_rows, monkeypatch, label, reason):
    def forbidden(*args, **kwargs):
        pytest.fail("Constant outcomes must never be fitted.")
    monkeypatch.setattr(gee_module, "GEE", forbidden)
    rows = [{**row, "label": label} for row in varying_rows]
    result = analyze_gee(rows)
    for fit in [result["combined"], *result["per_model"]]:
        assert fit["reason_code"] == reason and fit["status"] == "not_estimable"
        assert fit["converged"] is None
        assert all(coef["odds_ratio"] is None and coef["p_value"] is None for coef in fit["coefficients"])
        assert all(test["p_value"] is None for test in fit["joint_tests"])
    json.dumps(result, allow_nan=False)


def test_empty_data_has_explicit_no_data_status():
    result = analyze_gee([])
    assert result["combined"]["reason_code"] == "no_complete_triplets"
    assert result["per_model"] == []
    assert result["preparation"]["n_selected_responses"] == 0
    json.dumps(result, allow_nan=False)


def test_few_clusters_guard(varying_rows):
    rows = [row for row in varying_rows if int(row["claim_id"].split("-")[1]) % 8 == 0]
    result = analyze_gee(rows)
    assert result["combined"]["status"] == "inadequate"
    assert result["combined"]["reason_code"] == "too_few_clusters"
    assert result["combined"]["n_clusters"] == 16


def test_quasi_separation_detected_per_cell_before_fitting(varying_rows):
    rows = [{**row, "label": "SYCOPHANTIC"} if row["model"] == "gpt-6-luna" and row["confidence"] == "high" else row
            for row in varying_rows]
    result = analyze_gee(rows)
    fit = result["combined"]
    assert fit["reason_code"] == "separation"
    assert fit["separated_cells"] == [{"model": "gpt-6-luna", "confidence": "high", "n": 128, "n_events": 128}]
    assert all(coef["coefficient"] is None for coef in fit["coefficients"])
    assert next(fit for fit in result["per_model"] if fit["model"] == "z-model")["status"] == "ok"


def test_model_without_complete_blocks_causes_explicit_rank_deficiency(varying_rows):
    rows = [row for row in varying_rows if row["model"] == "gpt-6-luna" or row["confidence"] == "low"]
    result = analyze_gee(rows)
    assert result["preparation"]["model_levels"] == ["gpt-6-luna", "z-model"]
    assert result["combined"]["reason_code"] == "rank_deficient"
    assert next(fit for fit in result["per_model"] if fit["model"] == "z-model")["reason_code"] == "no_complete_triplets"


def test_sparse_event_clusters_not_treated_as_many_independent_responses(varying_rows):
    rows = [{**row, "label": "SYCOPHANTIC" if int(row["claim_id"].split("-")[1]) < 5 else "CORRECT"}
            for row in varying_rows]
    result = analyze_gee(rows)
    assert result["combined"]["n_events"] == 30
    assert result["combined"]["n_event_clusters"] == 5
    assert result["combined"]["reason_code"] == "sparse_outcome_clusters"
    assert result["combined"]["status"] == "inadequate"


def test_nonconvergence_suppresses_all_numerical_estimates(varying_rows, monkeypatch):
    class Nonconverged:
        def __init__(self, *args, **kwargs):
            pass
        def fit(self, **kwargs):
            return SimpleNamespace(converged=False, fit_history={"params": [0] * 100})
    monkeypatch.setattr(gee_module, "GEE", Nonconverged)
    fit = analyze_gee(varying_rows)["combined"]
    assert fit["reason_code"] == "nonconvergence"
    assert fit["converged"] is False and fit["iterations"] == 100
    assert all(coef["odds_ratio"] is None for coef in fit["coefficients"])


def test_nonfinite_fitted_values_suppressed_and_json_safe(varying_rows, monkeypatch):
    class Nonfinite:
        def __init__(self, y, x, **kwargs):
            self.p = x.shape[1]
        def fit(self, **kwargs):
            return SimpleNamespace(converged=True, fit_history={"params": [0]},
                                   params=np.full(self.p, np.nan), bse=np.ones(self.p), pvalues=np.ones(self.p),
                                   cov_params=lambda: np.eye(self.p), conf_int=lambda alpha: np.zeros((self.p, 2)),
                                   cov_struct=SimpleNamespace(dep_params=0.0))
    monkeypatch.setattr(gee_module, "GEE", Nonfinite)
    result = analyze_gee(varying_rows)
    assert result["combined"]["reason_code"] == "nonfinite_fit"
    assert all(coef["coefficient"] is None for coef in result["combined"]["coefficients"])
    json.dumps(result, allow_nan=False)


def test_fitting_exception_becomes_structured_unavailable_result(varying_rows, monkeypatch):
    def broken_fit(*args, **kwargs):
        raise np.linalg.LinAlgError("Synthetic test singularity")
    monkeypatch.setattr(gee_module, "GEE", broken_fit)
    result = analyze_gee(varying_rows)
    assert result["combined"]["reason_code"] == "fit_failed"
    assert "LinAlgError" in result["combined"]["reason"]
    assert result["combined"]["coefficients"][0]["odds_ratio"] is None
