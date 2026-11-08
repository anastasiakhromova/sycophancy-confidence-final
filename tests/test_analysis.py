"""Synthetic fixtures are tests only: no provider access and no report artifacts."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from sycophancy.analysis import (
    CONDITIONS, analyze_baseline, cluster_bootstrap, cluster_resample, cochran_q,
    evaluated_frame, exact_mcnemar, holm_correction, metric_table, paired_tests, prepare_paired,
)


def rows_from_patterns(patterns, models=("test-model",), repetitions=1):
    labels = {"C": "CORRECT", "U": "UNCERTAIN", "S": "SYCOPHANTIC"}
    return [
        {"response_id": f"{model}/{i}/{condition}/{repetition}", "claim_id": f"claim-{i:03d}",
         "model": model, "confidence": condition, "domain": "science" if i % 2 else "geography",
         "label": labels[pattern[condition_index]], "repetition": repetition,
         "needs_human_review": False, "difficulty": "easy"}
        for model in models for i, pattern in enumerate(patterns) for repetition in range(repetitions)
        for condition_index, condition in enumerate(CONDITIONS)
    ]


def table_row(table, **keys):
    return next(row for row in table if all(row.get(key) == value for key, value in keys.items()))


def test_metrics_counts_rates_and_domains():
    rows = rows_from_patterns(["CCS", "CUU", "SSS", "CCC"])
    rows[0]["needs_human_review"] = True
    table = metric_table(rows)
    low = table_row(table, confidence="low")
    assert low["n_responses"] == 4
    assert low["n_claims"] == 4
    assert low["needs_human_review"] == 1
    assert low["correction_rate"] == 0.75
    assert low["sycophancy_rate"] == 0.25
    assert low["uncertainty_rate"] == 0
    high = table_row(table, confidence="high")
    assert high["correction_rate"] == 0.25
    assert high["sycophancy_rate"] == 0.5
    assert high["uncertainty_rate"] == 0.25
    domain = metric_table(rows, ("model", "domain", "confidence"))
    assert table_row(domain, domain="geography", confidence="high")["sycophancy_rate"] == 1
    assert [row["confidence"] for row in table] == ["low", "neutral", "high"]


def test_dataframe_input_not_mutated_and_csv_types_supported():
    frame = pd.DataFrame(rows_from_patterns(["CCC"]))
    frame["repetition"] = "0"
    frame["needs_human_review"] = "false"
    original = frame.copy(deep=True)
    validated = evaluated_frame(frame)
    assert validated["repetition"].tolist() == [0, 0, 0]
    assert not validated["needs_human_review"].any()
    pd.testing.assert_frame_equal(frame, original)


def test_defaults_for_optional_columns():
    rows = rows_from_patterns(["CCC"])
    for row in rows:
        del row["repetition"], row["needs_human_review"], row["difficulty"]
    frame = evaluated_frame(rows)
    assert set(frame["repetition"]) == {0}
    assert set(frame["difficulty"]) == {"unspecified"}
    assert not frame["needs_human_review"].any()


@pytest.mark.parametrize("column,value", [
    ("confidence", "extreme"), ("label", "correct"), ("model", ""), ("claim_id", None),
    ("response_id", 123), ("repetition", -1), ("repetition", 0.5), ("repetition", True),
    ("needs_human_review", "maybe"), ("needs_human_review", 1), ("difficulty", "impossible"),
])
def test_rejects_malformed_rows(column, value):
    rows = rows_from_patterns(["CCC"])
    rows[0][column] = value
    with pytest.raises(ValueError):
        analyze_baseline(rows, n_bootstrap=10)


def test_missing_required_column_rejected():
    rows = rows_from_patterns(["CCC"])
    for row in rows:
        del row["label"]
    with pytest.raises(ValueError, match="Missing evaluated-response columns"):
        metric_table(rows)


@pytest.mark.parametrize("column", ["domain", "difficulty"])
def test_same_claim_metadata_must_agree_across_models(column):
    rows = rows_from_patterns(["CCC"], models=("a", "b"))
    rows[-1][column] = "technology" if column == "domain" else "hard"
    with pytest.raises(ValueError, match="Inconsistent"):
        prepare_paired(rows)


def test_duplicate_response_rejected():
    rows = rows_from_patterns(["CCC"])
    with pytest.raises(ValueError, match="Duplicate response_id"):
        prepare_paired(rows + rows[:1])


def test_duplicate_cell_rejected_even_with_distinct_response_id():
    rows = rows_from_patterns(["CCC"])
    duplicate = {**rows[0], "response_id": "new-id"}
    with pytest.raises(ValueError, match="Duplicate model/claim_id"):
        prepare_paired(rows + [duplicate])


def test_pairing_by_model_claim_repetition_and_missing_condition_exclusions():
    rows = rows_from_patterns(["CCS", "UUU"], models=("a", "b"), repetitions=2)
    rows = [row for row in rows if not (row["model"] == "b" and row["repetition"] == 1
                                      and row["claim_id"] == "claim-001" and row["confidence"] == "neutral")]
    paired = prepare_paired(rows)
    assert paired.report["n_complete_blocks"] == 7
    assert paired.report["n_excluded_blocks"] == 1
    assert paired.report["n_excluded_responses"] == 2
    assert paired.report["excluded_blocks"][0]["missing_conditions"] == ["neutral"]
    assert len(paired.complete) == 7
    assert paired.complete.iloc[0]["high"] == "SYCOPHANTIC"


def test_review_exclusion_drops_whole_triplet_and_preserves_denominators():
    rows = rows_from_patterns(["CCS", "CCC"])
    rows[0]["needs_human_review"] = True
    result = analyze_baseline(rows, include_review=False, n_bootstrap=20)
    assert result["metadata"]["n_selected_responses"] == 5
    assert result["paired"]["n_complete_blocks"] == 1
    assert result["paired"]["n_excluded_responses"] == 3
    assert result["paired"]["excluded_blocks"][0]["reason"] == "needs_human_review"
    assert table_row(result["rates_by_confidence"], confidence="high")["n_responses"] == 2
    assert table_row(result["paired_rates_by_confidence"], confidence="high")["n_responses"] == 1


def test_cochran_q_known_numeric_reference():
    # Column totals (0, 5, 8); sum(row totals squared)=23.
    # Q = 2*(3*(0**2+5**2+8**2)-13**2)/(3*13-23) = 12.25.
    values = [[0, 1, 1]] * 5 + [[0, 0, 1]] * 3 + [[0, 0, 0]] * 2
    result = cochran_q(values)
    assert result["statistic"] == pytest.approx(12.25)
    assert result["p_value"] == pytest.approx(math.exp(-12.25 / 2))
    assert result["df"] == 2
    assert result["n_discordant"] == 8
    assert result["small_sample_warning"] is True


@pytest.mark.parametrize("values", [[[0, 0, 0]] * 10, [[1, 1, 1]] * 10,
                                     [[0, 0, 0]] * 5 + [[1, 1, 1]] * 5])
def test_cochran_no_discordance_undefined_not_significant(values):
    result = cochran_q(values)
    assert result["statistic"] is None
    assert result["p_value"] is None
    assert result["status"] == "no_discordance"


def test_empty_q_has_no_result():
    result = cochran_q(np.empty((0, 3)))
    assert result["status"] == "no_data"
    assert result["p_value"] is None


def test_exact_mcnemar_numeric_reference_and_direction():
    result = exact_mcnemar([0] * 10, [1] * 8 + [0] * 2)
    assert result["table"] == [[2, 8], [0, 0]]
    assert result["p_value"] == pytest.approx(2 / 2**8)
    assert result["difference"] == 0.8
    reverse = exact_mcnemar([1] * 8 + [0] * 2, [0] * 10)
    assert reverse["p_value"] == result["p_value"]
    assert reverse["difference"] == -0.8


def test_exact_mcnemar_two_nonzero_discordant_cells():
    result = exact_mcnemar([0] * 9 + [1], [1] * 9 + [0])
    assert result["p_value"] == pytest.approx(22 / 1024)
    assert result["statistic"] == 1
    assert result["difference"] == 0.8


def test_exact_mcnemar_no_discordance_p_one_and_empty_no_data():
    result = exact_mcnemar([0, 1, 0], [0, 1, 0])
    assert result["p_value"] == 1
    assert result["difference"] == 0
    assert result["status"] == "no_discordance"
    assert exact_mcnemar([], [])["p_value"] is None


@pytest.mark.parametrize("values", [[[0, 1]], [[0, 1, 2]], [[0, np.nan, 1]], [0, 1, 1]])
def test_cochran_rejects_invalid_array(values):
    with pytest.raises(ValueError):
        cochran_q(values)


@pytest.mark.parametrize("first,second", [([0], [1, 1]), ([0, 2], [1, 1]), ([[0]], [[1]])])
def test_mcnemar_rejects_invalid_pairs(first, second):
    with pytest.raises(ValueError):
        exact_mcnemar(first, second)


def test_holm_known_values_preserves_order_and_monotonicity():
    assert holm_correction([0.04, 0.01, 0.03]) == pytest.approx([0.06, 0.03, 0.06])
    assert holm_correction([0.9, 0.8, 0.7]) == [1, 1, 1]
    assert holm_correction([]) == []


@pytest.mark.parametrize("values", [[-0.1], [1.01], [float("nan")], [[0.2]]])
def test_holm_rejects_invalid_probabilities(values):
    with pytest.raises(ValueError):
        holm_correction(values)


def test_paired_tests_reference_and_holm_family():
    rows = rows_from_patterns(["CSS"] * 5 + ["CCS"] * 3 + ["CCC"] * 2)
    result = paired_tests(prepare_paired(rows))
    q = table_row(result["cochran_q"], outcome="sycophancy")
    assert q["statistic"] == pytest.approx(12.25)
    high_low = table_row(result["mcnemar"], outcome="sycophancy", first="low", second="high")
    assert high_low["p_value"] == pytest.approx(0.0078125)
    assert high_low["p_holm"] == pytest.approx(0.0234375)
    assert high_low["holm_family_size"] == 3
    assert high_low["reject_holm_05"] is True


def test_repetitions_never_pooled_as_independent_claims():
    rows = rows_from_patterns(["CSS"] * 5 + ["CCC"] * 5, repetitions=3)
    result = paired_tests(prepare_paired(rows))
    assert len(result["cochran_q"]) == 9
    assert {row["n_blocks"] for row in result["cochran_q"]} == {10}
    assert len(result["mcnemar"]) == 27
    assert {row["holm_family_size"] for row in result["mcnemar"]} == {9}


def test_cluster_resample_preserves_models_conditions_and_repetitions():
    rows = rows_from_patterns(["CCC", "CCS", "SSS"], models=("a", "b"), repetitions=2)
    draw = cluster_resample(rows, seed=19)
    assert draw["_bootstrap_cluster"].nunique() == 3
    for _, group in draw.groupby("_bootstrap_cluster"):
        assert len(group) == 12
        assert group["claim_id"].nunique() == 1
        assert set(group["model"]) == {"a", "b"}
        assert set(group["confidence"]) == set(CONDITIONS)
        assert set(group["repetition"]) == {0, 1}


def test_cluster_bootstrap_not_individual_response_bootstrap():
    # 100 repeated measurements on 2 claims are still only 2 independent units.
    rows = rows_from_patterns(["CCC", "SSS"], repetitions=100)
    result = cluster_bootstrap(rows, n_bootstrap=500, seed=17)
    rate = table_row(result["rates"], outcome="sycophancy", confidence="low")
    assert rate["estimate"] == 0.5
    assert rate["n_claims"] == 2
    assert rate["n_blocks"] == 200
    assert rate["ci_lower"] == 0
    assert rate["ci_upper"] == 1
    for contrast in result["contrasts"]:
        assert contrast["estimate"] == 0
        assert contrast["ci_lower"] == 0
        assert contrast["ci_upper"] == 0
        assert contrast["status"] == "degenerate_empirical_distribution"


def test_bootstrap_estimand_remains_response_weighted_for_unequal_cluster_sizes():
    rows = rows_from_patterns(["CCC", "SSS"], repetitions=3)
    rows = [row for row in rows if row["claim_id"] == "claim-000" or row["repetition"] == 0]
    result = cluster_bootstrap(rows, n_bootstrap=100, seed=42)
    assert table_row(result["rates"], outcome="correction", confidence="low")["estimate"] == 0.75
    assert table_row(result["rates"], outcome="sycophancy", confidence="low")["estimate"] == 0.25


def test_bootstrap_pairs_conditions_so_identical_condition_effect_has_zero_ci():
    result = cluster_bootstrap(rows_from_patterns(["CCC"] * 20 + ["SSS"] * 20), n_bootstrap=200, seed=8)
    assert table_row(result["rates"], outcome="sycophancy", confidence="low")["ci_lower"] < 0.5
    contrast = table_row(result["contrasts"], outcome="sycophancy", contrast="high - low")
    assert contrast["ci_lower"] == contrast["ci_upper"] == 0


def test_bootstrap_all_models_share_claim_draws():
    rows = rows_from_patterns(["CCC"] * 10 + ["CCS"] * 10, models=("a", "b"))
    result = cluster_bootstrap(rows, n_bootstrap=100, seed=42)
    for table in [result["rates"], result["contrasts"]]:
        first = [{k: v for k, v in row.items() if k != "model"} for row in table if row["model"] == "a"]
        second = [{k: v for k, v in row.items() if k != "model"} for row in table if row["model"] == "b"]
        assert first == second


def test_bootstrap_estimates_contrast_orientation_and_is_reproducible():
    rows = rows_from_patterns(["CCS", "CUS", "SSS", "CCC"])
    first = cluster_bootstrap(rows, n_bootstrap=100, seed=23)
    second = cluster_bootstrap(list(reversed(rows)), n_bootstrap=100, seed=23)
    assert first == second
    assert table_row(first["contrasts"], outcome="sycophancy", contrast="high - low")["estimate"] == 0.5
    assert table_row(first["contrasts"], outcome="correction", contrast="high - low")["estimate"] == -0.5


def test_bootstrap_uses_complete_triplets_only():
    rows = rows_from_patterns(["CCS", "CCC", "SSS"])
    result = cluster_bootstrap(rows[:-1], n_bootstrap=100)
    assert result["n_clusters"] == 2
    assert table_row(result["rates"], outcome="sycophancy", confidence="low")["estimate"] == 0


def test_bootstrap_one_cluster_has_no_ci():
    result = cluster_bootstrap(rows_from_patterns(["CCS"]), n_bootstrap=10)
    assert all(row["ci_lower"] is None and row["ci_upper"] is None for row in result["rates"])
    assert {row["status"] for row in result["rates"]} == {"insufficient_clusters"}


@pytest.mark.parametrize("n_bootstrap", [0, -1, 1.5, True])
def test_bootstrap_rejects_invalid_replicate_count(n_bootstrap):
    with pytest.raises(ValueError):
        cluster_bootstrap([], n_bootstrap=n_bootstrap)


@pytest.mark.parametrize("include_review", [True, False])
def test_empty_analysis_remains_empty_and_json_safe(include_review):
    result = analyze_baseline([], n_bootstrap=10, include_review=include_review)
    assert result["metadata"]["n_observed_responses"] == 0
    assert result["rates_by_confidence"] == []
    assert result["cochran_q"] == []
    assert result["mcnemar"] == []
    assert result["bootstrap"]["rates"] == []
    json.dumps(result, allow_nan=False)


def test_full_result_json_safe_with_degenerate_outcomes():
    rows = rows_from_patterns(["CCC"] * 5 + ["CCS"] * 5, models=("a", "b"))
    result = analyze_baseline(rows, n_bootstrap=100)
    assert result["metadata"]["n_observed_responses"] == 60
    assert len(result["rates_by_difficulty"]) == 6
    assert len(result["rates_by_domain"]) == 12
    json.dumps(result, allow_nan=False)
