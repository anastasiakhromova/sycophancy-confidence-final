"""Plot tests use only synthetic in-test summaries and local temporary files."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pytest

from sycophancy.plots import (
    _effect_figure, _forest_figure, _heatmap_figure, _human_figure, _rates_figure, make_figures,
)


def summaries():
    rates = [{"model": "test-model", "confidence": confidence, "outcome": outcome,
              "estimate": value, "ci_lower": max(0, value - 0.1), "ci_upper": min(1, value + 0.1),
              "status": "ok"}
             for outcome, values in [("sycophancy", [0.1, 0.2, 0.3]), ("correction", [0.9, 0.8, 0.7])]
             for confidence, value in zip(("low", "neutral", "high"), values)]
    contrasts = [{"model": "test-model", "outcome": outcome, "contrast": "high - low",
                  "estimate": estimate, "ci_lower": estimate - 0.1, "ci_upper": estimate + 0.1,
                  "status": "ok"} for outcome, estimate in [("sycophancy", 0.2), ("correction", -0.2)]]
    domain = [{"model": "test-model", "domain": "science", "confidence": row["confidence"],
               "sycophancy_rate": row["estimate"]} for row in rates if row["outcome"] == "sycophancy"]
    analysis = {"bootstrap": {"rates": rates, "contrasts": contrasts}, "rates_by_domain": domain}
    gee = {"combined": {"status": "not_estimable", "reason": "No observed events.",
                         "coefficients": [{"term": "Intercept", "odds_ratio": None}]}}
    human = {"status": "no_human_labels", "n": 0, "confusion_matrix": None}
    return analysis, gee, human


def test_all_seven_png_and_pdf_files_are_valid_and_figures_closed(tmp_path):
    paths = make_figures(*summaries(), tmp_path)
    assert len(paths) == 14 and len(set(paths)) == 14
    assert sum(path.endswith(".png") for path in paths) == 7
    assert sum(path.endswith(".pdf") for path in paths) == 7
    for filename in paths:
        path = Path(filename)
        assert path.is_absolute() and path.stat().st_size > 1000
        expected = b"\x89PNG\r\n\x1a\n" if path.suffix == ".png" else b"%PDF-"
        assert path.read_bytes().startswith(expected)
    assert not plt.get_fignums()


def test_rate_curves_use_paired_bootstrap_population_not_available_case_rates():
    analysis, _, _ = summaries()
    analysis["rates_by_confidence"] = [{"model": "test-model", "confidence": "low", "sycophancy_rate": 0.99}]
    fig = _rates_figure(analysis, "sycophancy")
    try:
        assert fig.axes[0].lines[0].get_ydata() == pytest.approx([0.1, 0.2, 0.3])
        assert "Complete triplets" in fig.texts[0].get_text()
    finally:
        plt.close(fig)


def test_paired_effect_axis_is_percentage_points():
    analysis, _, _ = summaries()
    fig = _effect_figure(analysis)
    try:
        assert fig.axes[0].lines[0].get_xdata()[0] == pytest.approx(20)
        assert fig.axes[0].lines[1].get_xdata()[0] == pytest.approx(-20)
        assert "percentage points" in fig.axes[0].get_xlabel()
    finally:
        plt.close(fig)


def test_heatmap_missing_condition_is_masked_not_zero():
    analysis, _, _ = summaries()
    analysis["bootstrap"]["rates"] = [row for row in analysis["bootstrap"]["rates"] if row["confidence"] != "high"]
    fig = _heatmap_figure(analysis)
    try:
        values = fig.axes[0].images[0].get_array()
        assert np.ma.getmaskarray(values)[0, 2]
        assert "Unavailable" in [text.get_text() for text in fig.axes[0].texts]
    finally:
        plt.close(fig)


def test_unavailable_or_forest_has_no_invented_estimates():
    _, gee, _ = summaries()
    fig = _forest_figure(gee)
    try:
        assert not fig.axes[0].lines
        assert "not estimable" in fig.axes[0].get_title()
        assert "No observed events" in fig.axes[0].texts[0].get_text()
    finally:
        plt.close(fig)


def test_estimable_or_forest_plots_supplied_or_with_log_scale():
    gee = {"combined": {"status": "ok", "model_reference": "test-model", "coefficients": [
        {"term": "Intercept", "odds_ratio": 0.1, "or_ci_lower": 0.05, "or_ci_upper": 0.2},
        {"term": "C(confidence)[T.high]", "odds_ratio": 2, "or_ci_lower": 1.2, "or_ci_upper": 3.5},
    ]}}
    fig = _forest_figure(gee)
    try:
        ax = fig.axes[0]
        assert ax.get_xscale() == "log"
        assert ax.lines[0].get_xdata()[0] == 2
        assert len(ax.get_yticklabels()) == 1  # Intercept excluded, no OR=0 substitution.
    finally:
        plt.close(fig)


def test_no_human_labels_produces_pending_text_not_zero_counts():
    _, _, human = summaries()
    fig = _human_figure(human)
    try:
        assert not fig.axes[0].images
        assert "pending" in fig.axes[0].get_title()
        assert "No completed human labels" in fig.axes[0].texts[0].get_text()
    finally:
        plt.close(fig)


def test_actual_confusion_orientation_and_counts_preserved():
    human = {"n": 6, "labels": ["CORRECT", "UNCERTAIN", "SYCOPHANTIC"],
             "confusion_matrix": [[1, 2, 0], [0, 1, 0], [0, 0, 2]]}
    fig = _human_figure(human)
    try:
        ax = fig.axes[0]
        assert np.asarray(ax.images[0].get_array()).tolist() == human["confusion_matrix"]
        assert ax.get_xlabel() == "Automatic evaluator" and ax.get_ylabel() == "Human evaluator"
    finally:
        plt.close(fig)


def test_empty_inputs_show_unavailable_figures_without_fake_data(tmp_path):
    paths = make_figures({}, {}, {}, tmp_path)
    assert len(paths) == 14
    assert not plt.get_fignums()
