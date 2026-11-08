"""Seven headless research figures, each saved as PNG and PDF.

Unavailable estimates remain visibly unavailable. Condition-rate figures and
the model heatmap use the complete-triplet bootstrap population; domain rates
describe all available evaluated responses. Empty human annotations never become
a zero-filled confusion matrix. No provider calls or inference occur here.
"""

from __future__ import annotations

from pathlib import Path
import textwrap
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter
import numpy as np


CONDITIONS = ("low", "neutral", "high")
PALETTE = ("#2166ac", "#d6604d", "#1b7837", "#762a83", "#8c510a")
LABELS = {"correction": "Correction", "sycophancy": "Sycophancy", "uncertainty": "Uncertainty"}


def _models(rows: list[dict]) -> list[str]:
    models = sorted({row["model"] for row in rows})
    return (["gpt-6-luna"] if "gpt-6-luna" in models else []) + [model for model in models if model != "gpt-6-luna"]


def _unavailable(ax, title: str, message: str) -> None:
    ax.set_title(title, fontsize=14, pad=18)
    ax.set_axis_off()
    ax.text(0.5, 0.55, textwrap.fill(message, 88), transform=ax.transAxes,
            ha="center", va="center", fontsize=12, linespacing=1.6)


def _footnote(fig, text: str) -> None:
    fig.text(0.02, 0.015, text, fontsize=8, color="#444444", ha="left", va="bottom")


def _save(fig, directory: Path, stem: str) -> list[str]:
    paths = []
    try:
        for suffix in ("png", "pdf"):
            path = directory / f"{stem}.{suffix}"
            fig.savefig(path, dpi=160, bbox_inches="tight", facecolor="white")
            paths.append(str(path.resolve()))
    finally:
        plt.close(fig)
    return paths


def _rates_figure(analysis: dict, outcome: str):
    rows = [row for row in analysis.get("bootstrap", {}).get("rates", []) if row["outcome"] == outcome]
    models = _models(rows)
    fig, ax = plt.subplots(figsize=(8, 4.8))
    if not rows:
        _unavailable(ax, f"{LABELS[outcome]} rate by confidence", "No complete eligible claim triplets; rates and cluster confidence intervals are unavailable.")
        return fig
    missing_ci = False
    for index, model in enumerate(models):
        mapping = {row["confidence"]: row for row in rows if row["model"] == model}
        xs = np.arange(3, dtype=float) + (index - (len(models) - 1) / 2) * 0.075
        ys = [mapping.get(condition, {}).get("estimate", np.nan) for condition in CONDITIONS]
        color = PALETTE[index % len(PALETTE)]
        ax.plot(xs, ys, marker="o", markersize=6, color=color, label=model, linewidth=1.6)
        for x, condition in zip(xs, CONDITIONS):
            row = mapping.get(condition)
            if row and row.get("ci_lower") is not None and row.get("ci_upper") is not None:
                ax.vlines(x, row["ci_lower"], row["ci_upper"], color=color, linewidth=1.5)
                ax.hlines([row["ci_lower"], row["ci_upper"]], x - 0.025, x + 0.025, color=color, linewidth=1.5)
            elif row:
                missing_ci = True
    ax.set(title=f"{LABELS[outcome]} rate by confidence", xlabel="Expressed user confidence", ylabel=f"{LABELS[outcome]} rate",
           xticks=np.arange(3), xticklabels=[condition.upper() for condition in CONDITIONS], ylim=(-0.04, 1.04), xlim=(-0.25, 2.25))
    ax.yaxis.set_major_formatter(PercentFormatter(1))
    ax.grid(axis="y", alpha=0.2)
    ax.legend(loc="best", frameon=False, fontsize=9)
    note = "Provisional automatic labels; these outcome rates have not been human-validated.\n"
    note += "Complete triplets; claim-cluster 95% percentile CIs. Degenerate empirical CIs do not establish equivalence."
    if missing_ci:
        note += " Some CIs unavailable."
    if all(row.get("estimate") == 0 for row in rows):
        note += "\nAll displayed model curves lie at zero; coincident curves overlap."
    _footnote(fig, note)
    fig.tight_layout(rect=(0, 0.13, 1, 1))
    return fig


def _effect_figure(analysis: dict):
    rows = [row for row in analysis.get("bootstrap", {}).get("contrasts", [])
            if row["contrast"] == "high - low" and row["outcome"] in {"sycophancy", "correction"}]
    models = _models(rows)
    rows = sorted(rows, key=lambda row: (models.index(row["model"]), ("sycophancy", "correction").index(row["outcome"])))
    fig, ax = plt.subplots(figsize=(9, max(3.6, 0.5 * len(rows) + 1.8)))
    if not rows:
        _unavailable(ax, "HIGH minus LOW effects", "No complete eligible triplets; paired rate differences are unavailable.")
        return fig
    limits = [0.0]
    missing_ci = False
    for index, row in enumerate(rows):
        color = PALETTE[0] if row["outcome"] == "sycophancy" else PALETTE[1]
        estimate = 100 * row["estimate"]
        ax.plot(estimate, index, "o", color=color)
        limits.append(estimate)
        if row.get("ci_lower") is not None and row.get("ci_upper") is not None:
            lower, upper = 100 * row["ci_lower"], 100 * row["ci_upper"]
            ax.hlines(index, lower, upper, color=color, linewidth=1.7)
            ax.vlines([lower, upper], index - 0.07, index + 0.07, color=color, linewidth=1.7)
            limits.extend([lower, upper])
        else:
            missing_ci = True
            ax.annotate(" CI unavailable", (estimate, index), xytext=(5, 5), textcoords="offset points", fontsize=8)
    span = max(max(limits) - min(limits), 2.0)
    ax.set_xlim(min(limits) - 0.12 * span, max(limits) + 0.25 * span)
    ax.set_yticks(np.arange(len(rows)), [f"{row['model']} — {LABELS[row['outcome']]}" for row in rows])
    ax.set(title="HIGH minus LOW: paired rate differences", xlabel="Difference (percentage points)")
    ax.axvline(0, color="#666666", linewidth=1, linestyle="--")
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.2)
    _footnote(fig, "Provisional automatic labels; these outcome differences have not been human-validated.\n"
              + "Complete triplets; claim-cluster 95% percentile CIs. Zero-width empirical CIs do not establish equivalence."
              + (" Some CIs unavailable." if missing_ci else ""))
    fig.tight_layout(rect=(0, 0.11, 1, 1))
    return fig


def _domain_figure(analysis: dict):
    rows = analysis.get("rates_by_domain", [])
    models = _models(rows)
    fig, axes = plt.subplots(1, max(1, len(models)), figsize=(max(7, len(models) * 4.1), 4.8), squeeze=False, sharey=True)
    if not models:
        _unavailable(axes[0, 0], "Domain by confidence", "No evaluated domain-level responses are available.")
        return fig
    domains = sorted({row["domain"] for row in rows})
    for ax, model in zip(axes[0], models):
        for index, domain in enumerate(domains):
            mapping = {row["confidence"]: row for row in rows if row["model"] == model and row["domain"] == domain}
            if not mapping:
                continue
            values = [mapping.get(condition, {}).get("sycophancy_rate", np.nan) for condition in CONDITIONS]
            ax.plot(np.arange(3), values, marker="o", markersize=4, linewidth=1.3,
                    color=PALETTE[index % len(PALETTE)], label=domain.replace("_", " "))
        ax.set(title=model, xticks=np.arange(3), xticklabels=[condition.upper() for condition in CONDITIONS],
               xlabel="User confidence", ylim=(-0.04, 1.04))
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.grid(axis="y", alpha=0.2)
    axes[0, 0].set_ylabel("Sycophancy rate")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, 0.96), ncol=min(5, len(domains)), frameon=False, fontsize=8)
    fig.suptitle("Domain × confidence", fontsize=14, y=1.02)
    note = "Provisional automatic labels; these outcome rates have not been human-validated.\n"
    note += "All available evaluated responses; domain rates are descriptive, without domain-level confidence intervals."
    if all(row.get("sycophancy_rate") == 0 for row in rows):
        note += "\nAll displayed domain curves lie at zero; coincident curves overlap."
    _footnote(fig, note)
    fig.tight_layout(rect=(0, 0.13, 1, 0.91))
    return fig


def _heatmap_figure(analysis: dict):
    rows = [row for row in analysis.get("bootstrap", {}).get("rates", []) if row["outcome"] == "sycophancy"]
    models = _models(rows)
    fig, ax = plt.subplots(figsize=(7.5, max(3.3, len(models) * 0.65 + 2)))
    if not models:
        _unavailable(ax, "Model × confidence: sycophancy", "No complete eligible claim triplets; no observed rate cells to display.")
        return fig
    matrix = np.full((len(models), len(CONDITIONS)), np.nan)
    for row in rows:
        matrix[models.index(row["model"]), CONDITIONS.index(row["confidence"])] = row["estimate"]
    cmap = plt.get_cmap("YlOrRd").copy()
    cmap.set_bad("#eeeeee")
    im = ax.imshow(np.ma.masked_invalid(matrix), vmin=0, vmax=1, cmap=cmap, aspect="auto")
    for i in range(len(models)):
        for j in range(3):
            value = matrix[i, j]
            ax.text(j, i, "Unavailable" if not np.isfinite(value) else f"{100 * value:.1f}%",
                    ha="center", va="center", color="white" if value > 0.6 else "black", fontsize=11)
    ax.set(title="Model × confidence: sycophancy rate", xticks=np.arange(3),
           xticklabels=[condition.upper() for condition in CONDITIONS], yticks=np.arange(len(models)), yticklabels=models)
    fig.colorbar(im, ax=ax, format=PercentFormatter(1), label="Sycophancy rate")
    _footnote(fig, "Complete-triplet population; blank cells mean unavailable, not zero. Labels remain provisional.")
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    return fig


def _forest_figure(gee: dict):
    fit = gee.get("combined", {})
    rows = [row for row in fit.get("coefficients", []) if row.get("term") != "Intercept"]
    fig, ax = plt.subplots(figsize=(10, max(4, len(rows) * 0.42 + 2)))
    if fit.get("status") != "ok" or not rows:
        reason = fit.get("reason") or "No estimable combined logistic GEE was supplied."
        _unavailable(ax, "GEE odds ratios: not estimable", f"Status: {fit.get('status', 'unavailable')}. {reason} No odds ratios or confidence intervals are substituted.")
        return fig
    valid = all(all(row.get(key) is not None and np.isfinite(row[key]) and row[key] > 0
                    for key in ("odds_ratio", "or_ci_lower", "or_ci_upper")) for row in rows)
    if not valid:
        _unavailable(ax, "GEE odds ratios: unavailable", "The supplied coefficient table contains missing or nonfinite odds ratios or bounds. No point estimates are drawn.")
        return fig
    for index, row in enumerate(rows):
        ax.hlines(index, row["or_ci_lower"], row["or_ci_upper"], color=PALETTE[0], linewidth=1.5)
        ax.plot(row["odds_ratio"], index, "o", color=PALETTE[0])
    ax.axvline(1, color="#666666", linestyle="--", linewidth=1)
    ax.set_xscale("log")
    ax.set_yticks(np.arange(len(rows)), [row["term"].replace("C(confidence)[T.", "confidence=").replace("C(model)[T.", "model=").replace("]", "").replace(":", " × ") for row in rows])
    ax.set(title="Combined logistic GEE: odds ratios", xlabel="Odds ratio (logarithmic scale), robust 95% CI")
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.2)
    _footnote(fig, f"Reference: LOW / {fit.get('model_reference')}. Cluster: claim_id; exchangeable working correlation; robust sandwich covariance.")
    fig.tight_layout(rect=(0, 0.065, 1, 1))
    return fig


def _human_figure(human: dict):
    fig, ax = plt.subplots(figsize=(7, 5.2))
    if not human.get("n") or human.get("confusion_matrix") is None:
        _unavailable(ax, "Human validation pending", "No completed human labels are available. A confusion matrix and evaluator agreement cannot yet be estimated.")
        return fig
    labels = human.get("labels", [])
    matrix = np.asarray(human["confusion_matrix"], dtype=float)
    if matrix.shape != (len(labels), len(labels)) or not labels or not np.isfinite(matrix).all() or np.any(matrix < 0) or not np.all(matrix == np.floor(matrix)) or matrix.sum() != human["n"]:
        raise ValueError("Human confusion matrix must contain nonnegative observed counts summing to n.")
    im = ax.imshow(matrix, cmap="Blues", vmin=0)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, str(int(matrix[i, j])), ha="center", va="center",
                    color="white" if matrix[i, j] > matrix.max() * 0.55 else "black", fontsize=12)
    ax.set(title=f"Automatic vs human labels (n={human['n']})", xlabel="Automatic evaluator", ylabel="Human evaluator",
           xticks=np.arange(len(labels)), xticklabels=labels, yticks=np.arange(len(labels)), yticklabels=labels)
    ax.tick_params(axis="x", labelrotation=15)
    fig.colorbar(im, ax=ax, label="Observed responses")
    _footnote(fig, "Rows: human labels; columns: automatic labels. Stratified sample agreement is not population-weighted accuracy.")
    fig.tight_layout(rect=(0, 0.065, 1, 1))
    return fig


def make_figures(analysis: dict[str, Any], gee: dict[str, Any], human: dict[str, Any],
                 output_dir: str | Path) -> list[str]:
    """Save 7 actual-data or explicitly unavailable panels as 14 PNG/PDF paths.

    ``analysis`` follows analyze_baseline, ``gee`` follows analyze_gee, and
    ``human`` follows agreement_metrics. This function never invents observations
    to fill an absent model, confidence condition, coefficient, or annotation.
    """
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    makers = [
        ("01_sycophancy_by_confidence", lambda: _rates_figure(analysis, "sycophancy")),
        ("02_correction_by_confidence", lambda: _rates_figure(analysis, "correction")),
        ("03_high_low_effect", lambda: _effect_figure(analysis)),
        ("04_domain_by_confidence", lambda: _domain_figure(analysis)),
        ("05_model_confidence_heatmap", lambda: _heatmap_figure(analysis)),
        ("06_odds_ratio_forest", lambda: _forest_figure(gee)),
        ("07_human_confusion_matrix", lambda: _human_figure(human)),
    ]
    for stem, make in makers:
        paths.extend(_save(make(), output_dir, stem))
    return paths
