"""Paired baseline inference on evaluated, observed responses.

Public entry point ``analyze_baseline`` accepts records or a pandas DataFrame and
returns JSON-safe tables. Rates use *all available* selected responses; inference
and bootstrap use only complete model/claim/repetition triplets. Review flags are
included by default and explicitly counted: automatic labels are provisional.

The bootstrap resamples claim IDs once per draw across all models, conditions,
and repetitions. It estimates response-weighted rates, preserving unequal cluster
sizes. CIs are percentile intervals, not simultaneous intervals. Constant empirical
outcomes produce degenerate CIs; these do not establish population certainty.

Cochran Q and exact McNemar require independent blocks. Consequently repetitions
are tested separately, never pooled as independent claims. Holm corrects all
pairwise tests (including repetitions) within each model/outcome family.

Method references (checked 2026-10-06):
https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.cochrans_q.html
https://www.statsmodels.org/stable/generated/statsmodels.stats.contingency_tables.mcnemar.html
https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html
https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from numbers import Integral
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.stats import binomtest
from statsmodels.stats.contingency_tables import cochrans_q as _statsmodels_q
from statsmodels.stats.multitest import multipletests


CONDITIONS = ("low", "neutral", "high")
OUTCOMES = {"correction": "CORRECT", "sycophancy": "SYCOPHANTIC", "uncertainty": "UNCERTAIN"}
CONTRASTS = (("high", "low"), ("high", "neutral"), ("neutral", "low"))
BLOCK_COLUMNS = ["model", "claim_id", "repetition"]
REQUIRED_COLUMNS = ["response_id", "claim_id", "model", "confidence", "domain", "label"]
Records = pd.DataFrame | Iterable[Mapping[str, Any]]


def _boolean(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, str) and value.casefold() in {"true", "false"}:
        return value.casefold() == "true"
    raise ValueError("needs_human_review must be a boolean (or CSV 'true'/'false').")


def evaluated_frame(rows: Records) -> pd.DataFrame:
    """Copy and validate evaluated rows; reject ambiguous or duplicate cells.

    ``confidence`` is the experiment condition, not evaluator confidence. The
    latter must be saved under ``evaluation_confidence`` or another distinct key.
    One call represents a single analysis population; do not concatenate runs
    with overlapping model/claim/condition/repetition keys.
    """
    frame = rows.copy(deep=True) if isinstance(rows, pd.DataFrame) else pd.DataFrame(list(rows))
    if frame.empty:
        frame = pd.DataFrame(columns=REQUIRED_COLUMNS + ["repetition", "needs_human_review", "difficulty"])
        frame["needs_human_review"] = pd.Series(dtype=bool)
        frame["repetition"] = pd.Series(dtype=int)
        return frame
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing evaluated-response columns: {', '.join(missing)}")
    for column in REQUIRED_COLUMNS:
        if frame[column].isna().any() or not frame[column].map(
            lambda value: isinstance(value, str) and bool(value.strip())
        ).all():
            raise ValueError(f"{column} must contain nonempty strings.")
    frame["confidence"] = frame["confidence"].map(lambda value: value.lower())
    if not frame["confidence"].isin(CONDITIONS).all():
        raise ValueError("confidence must be low, neutral, or high.")
    if not frame["label"].isin(OUTCOMES.values()).all():
        raise ValueError("label must be CORRECT, UNCERTAIN, or SYCOPHANTIC.")
    if "repetition" not in frame:
        frame["repetition"] = 0
    def repetition_number(value: Any) -> int:
        if isinstance(value, str) and value.isdigit():
            value = int(value)
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral) or value < 0:
            raise ValueError("repetition must be a nonnegative integer.")
        return int(value)
    frame["repetition"] = frame["repetition"].map(repetition_number)
    frame["needs_human_review"] = (
        frame["needs_human_review"].map(_boolean) if "needs_human_review" in frame else False
    )
    if "difficulty" not in frame:
        frame["difficulty"] = "unspecified"
    frame["difficulty"] = frame["difficulty"].fillna("unspecified")
    if not frame["difficulty"].isin(["easy", "medium", "hard", "unspecified"]).all():
        raise ValueError("difficulty must be easy, medium, hard, or unspecified.")
    if frame["response_id"].duplicated().any():
        raise ValueError("Duplicate response_id; responses must be counted once.")
    if frame.duplicated(BLOCK_COLUMNS + ["confidence"]).any():
        raise ValueError("Duplicate model/claim_id/repetition/confidence cells.")
    for column in ["domain", "difficulty"]:
        if (frame.groupby("claim_id")[column].nunique() > 1).any():
            raise ValueError(f"Inconsistent {column} metadata for the same claim_id.")
    return frame.sort_values(BLOCK_COLUMNS + ["confidence"], kind="stable").reset_index(drop=True)


def _metric_table(frame: pd.DataFrame, group_by: Sequence[str]) -> list[dict[str, Any]]:
    if not group_by or any(column not in frame for column in group_by):
        raise ValueError("group_by must name one or more available columns.")
    table = []
    for key, group in frame.groupby(list(group_by), dropna=False, sort=True):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(group_by, key))
        row.update(n_responses=int(len(group)), n_claims=int(group["claim_id"].nunique()),
                   needs_human_review=int(group["needs_human_review"].sum()))
        for outcome, label in OUTCOMES.items():
            count = int((group["label"] == label).sum())
            row[f"{outcome}_count"] = count
            row[f"{outcome}_rate"] = count / len(group)
        table.append(row)
    order = {value: index for index, value in enumerate(CONDITIONS)}
    return sorted(table, key=lambda row: tuple(order[row[col]] if col == "confidence" else row[col]
                                             for col in group_by))


def metric_table(rows: Records, group_by: Sequence[str] = ("model", "confidence")) -> list[dict[str, Any]]:
    """Descriptive rates of observed labels, including explicit denominators."""
    return _metric_table(evaluated_frame(rows), group_by)


@dataclass
class PairedDataset:
    """``complete`` is wide (label columns low/neutral/high); ``report`` is JSON-safe."""

    complete: pd.DataFrame
    report: dict[str, Any]


def _prepare_paired(frame: pd.DataFrame, include_review: bool) -> PairedDataset:
    complete: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for key, group in frame.groupby(BLOCK_COLUMNS, sort=True):
        base = dict(zip(BLOCK_COLUMNS, key))
        base["repetition"] = int(base["repetition"])
        present = set(group["confidence"])
        missing = [condition for condition in CONDITIONS if condition not in present]
        reviewed = int(group["needs_human_review"].sum())
        if missing or (reviewed and not include_review):
            excluded.append({**base, "missing_conditions": missing, "n_observed": int(len(group)),
                             "needs_human_review": reviewed,
                             "reason": "missing_conditions" if missing else "needs_human_review"})
            continue
        labels = group.set_index("confidence")["label"]
        complete.append({**base, "domain": group["domain"].iloc[0],
                         "difficulty": group["difficulty"].iloc[0], "needs_human_review": reviewed,
                         **{condition: labels[condition] for condition in CONDITIONS}})
    wide = pd.DataFrame(complete, columns=BLOCK_COLUMNS + ["domain", "difficulty", "needs_human_review", *CONDITIONS])
    report = {"n_observed_responses": int(len(frame)), "n_complete_blocks": len(complete),
              "n_complete_claims": int(wide["claim_id"].nunique()), "n_excluded_blocks": len(excluded),
              "n_excluded_responses": sum(row["n_observed"] for row in excluded),
              "included_review_flags": include_review, "excluded_blocks": excluded,
              "block_key": BLOCK_COLUMNS, "conditions": list(CONDITIONS)}
    return PairedDataset(wide, report)


def prepare_paired(rows: Records, *, include_review: bool = True) -> PairedDataset:
    """Require all 3 conditions per block; never impute a missing response.

    If ``include_review=False``, one flagged response excludes its entire block.
    Exclusions are reported relative to observed blocks; absent planned blocks
    cannot be inferred without the experiment manifest.
    """
    return _prepare_paired(evaluated_frame(rows), include_review)


def _binary_matrix(values: Any, *, columns: int | None = None) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 2 or (columns is not None and array.shape[1] != columns):
        raise ValueError(f"Expected a two-dimensional binary array{f' with {columns} columns' if columns else ''}.")
    if not np.isin(array, [0, 1]).all():
        raise ValueError("Statistical outcomes must be binary, with no missing observations.")
    return array.astype(np.int64)


def cochran_q(values: Any) -> dict[str, Any]:
    """Q across the 3 columns low/neutral/high, with independent claim rows.

    P-values use the asymptotic chi-square approximation; small numbers of
    discordant claims are explicitly flagged. With no discordance Q is undefined.
    """
    array = _binary_matrix(values, columns=3)
    discordant = int(np.count_nonzero((array.sum(axis=1) > 0) & (array.sum(axis=1) < 3)))
    result = {"n_blocks": int(len(array)), "n_discordant": discordant, "df": 2,
              "method": "Cochran Q; asymptotic chi-square", "statistic": None, "p_value": None,
              "status": "no_data" if len(array) == 0 else "no_discordance",
              "small_sample_warning": discordant < 10}
    if discordant:
        statistic = _statsmodels_q(array)
        result.update(statistic=float(statistic.statistic), p_value=float(statistic.pvalue), status="ok")
    return result


def exact_mcnemar(first: Sequence[int], second: Sequence[int]) -> dict[str, Any]:
    """Two-sided exact binomial McNemar; effect is mean(second)-mean(first).

    The table rows are first=0/1 and columns second=0/1. Zero discordance has
    p=1 by definition; this is no evidence of a difference, not equivalence.
    """
    if np.asarray(first).ndim != 1 or np.asarray(second).ndim != 1 or len(first) != len(second):
        raise ValueError("McNemar requires two paired one-dimensional vectors of equal length.")
    array = _binary_matrix(np.column_stack([first, second]), columns=2)
    table = np.zeros((2, 2), dtype=np.int64)
    for left, right in array:
        table[left, right] += 1
    gained, lost = int(table[0, 1]), int(table[1, 0])
    discordant = gained + lost
    return {"n_blocks": int(len(array)), "table": table.tolist(), "gained": gained, "lost": lost,
            "n_discordant": discordant, "statistic": min(gained, lost),
            "p_value": (float(binomtest(gained, discordant, p=0.5, alternative="two-sided").pvalue)
                        if discordant else (1.0 if len(array) else None)),
            "difference": (gained - lost) / len(array) if len(array) else None,
            "method": "McNemar exact binomial; two-sided",
            "status": "ok" if discordant else ("no_discordance" if len(array) else "no_data")}


def holm_correction(p_values: Sequence[float]) -> list[float]:
    """Holm step-down adjusted p-values in the original input order."""
    array = np.asarray(p_values, dtype=float)
    if array.ndim != 1 or not np.isfinite(array).all() or np.any((array < 0) | (array > 1)):
        raise ValueError("p_values must be finite probabilities in [0, 1].")
    if not len(array):
        return []
    return multipletests(array, method="holm")[1].astype(float).tolist()


def paired_tests(paired: PairedDataset) -> dict[str, list[dict[str, Any]]]:
    """Test each model/repetition; Holm family = model x outcome across repetitions."""
    q_tests, mcnemar_tests = [], []
    for (model, repetition), group in paired.complete.groupby(["model", "repetition"], sort=True):
        for outcome, label in OUTCOMES.items():
            base = {"model": model, "repetition": int(repetition), "outcome": outcome}
            values = (group[list(CONDITIONS)].to_numpy() == label).astype(int)
            q_tests.append({**base, **cochran_q(values)})
            for first, second in combinations(range(3), 2):
                mcnemar_tests.append({**base, "first": CONDITIONS[first], "second": CONDITIONS[second],
                                      "contrast": f"{CONDITIONS[second]} - {CONDITIONS[first]}",
                                      **exact_mcnemar(values[:, first], values[:, second])})
    for model in sorted({row["model"] for row in mcnemar_tests}):
        for outcome in OUTCOMES:
            family = [row for row in mcnemar_tests if row["model"] == model and row["outcome"] == outcome]
            adjusted = holm_correction([row["p_value"] for row in family])
            for row, value in zip(family, adjusted):
                row.update(p_holm=value, reject_holm_05=value <= 0.05, holm_family_size=len(family),
                           holm_family=f"{model} / {outcome}")
    return {"cochran_q": q_tests, "mcnemar": mcnemar_tests}


def cluster_resample(rows: Records, *, seed: int = 42) -> pd.DataFrame:
    """One inspectable claim bootstrap draw, preserving every row in each cluster.

    Repeated draws receive distinct ``_bootstrap_cluster`` IDs. This resample
    intentionally repeats response IDs and must not pass through input validation
    again. The production bootstrap uses equivalent weighted cluster sums.
    """
    frame = evaluated_frame(rows)
    claims = sorted(frame["claim_id"].unique())
    if not claims:
        return frame.assign(_bootstrap_cluster=pd.Series(dtype=int))
    draw = np.random.default_rng(seed).choice(claims, size=len(claims), replace=True)
    return pd.concat([frame[frame["claim_id"] == claim].assign(_bootstrap_cluster=index)
                      for index, claim in enumerate(draw)], ignore_index=True)


def _interval(values: np.ndarray, estimate: float, n_clusters: int, level: float) -> dict[str, Any]:
    values = values[np.isfinite(values)]
    if n_clusters < 2 or not len(values):
        return {"estimate": estimate, "ci_lower": None, "ci_upper": None,
                "n_bootstrap_valid": len(values), "status": "insufficient_clusters"}
    alpha = (1 - level) / 2
    lower, upper = np.quantile(values, [alpha, 1 - alpha])
    return {"estimate": estimate, "ci_lower": float(lower), "ci_upper": float(upper),
            "n_bootstrap_valid": len(values),
            "status": "degenerate_empirical_distribution" if np.ptp(values) == 0 else "ok"}


def _bootstrap(paired: PairedDataset, *, n_bootstrap: int, seed: int, level: float) -> dict[str, Any]:
    if isinstance(n_bootstrap, bool) or not isinstance(n_bootstrap, Integral) or n_bootstrap < 1:
        raise ValueError("n_bootstrap must be a positive integer.")
    if not 0 < level < 1:
        raise ValueError("level must be between 0 and 1.")
    wide = paired.complete
    claims = sorted(wide["claim_id"].unique())
    models = sorted(wide["model"].unique())
    output: dict[str, Any] = {"method": "claim-cluster percentile bootstrap", "cluster": "claim_id",
                             "n_bootstrap": int(n_bootstrap), "seed": int(seed), "level": level,
                             "n_clusters": len(claims), "population": "complete_triplets",
                             "estimand": "response-weighted rate within each model",
                             "rates": [], "contrasts": []}
    if not claims:
        return output
    # One global resampling matrix is shared by every model/outcome/condition.
    # Multiplicity weights preserve all repetitions of each selected claim.
    weights = np.random.default_rng(seed).multinomial(len(claims), np.full(len(claims), 1 / len(claims)),
                                                     size=int(n_bootstrap))
    for model in models:
        model_rows = wide[wide["model"] == model]
        counts = model_rows.groupby("claim_id").size().reindex(claims, fill_value=0).to_numpy()
        denominators = weights @ counts
        n_clusters = int(np.count_nonzero(counts))
        for outcome, label in OUTCOMES.items():
            successes = (model_rows.set_index("claim_id")[list(CONDITIONS)] == label).astype(int)
            totals = successes.groupby(level=0).sum().reindex(claims, fill_value=0).to_numpy()
            numerators = weights @ totals
            draws = np.divide(numerators, denominators[:, None],
                              out=np.full(numerators.shape, np.nan, dtype=float), where=denominators[:, None] != 0)
            estimates = totals.sum(axis=0) / counts.sum()
            base = {"model": model, "outcome": outcome, "n_claims": n_clusters,
                    "n_blocks": int(counts.sum())}
            for index, condition in enumerate(CONDITIONS):
                output["rates"].append({**base, "confidence": condition,
                                         **_interval(draws[:, index], float(estimates[index]), n_clusters, level)})
            for later, earlier in CONTRASTS:
                left, right = CONDITIONS.index(later), CONDITIONS.index(earlier)
                output["contrasts"].append({**base, "contrast": f"{later} - {earlier}",
                                             **_interval(draws[:, left] - draws[:, right],
                                                         float(estimates[left] - estimates[right]), n_clusters, level)})
    return output


def cluster_bootstrap(rows: Records, *, n_bootstrap: int = 2000, seed: int = 42,
                      level: float = 0.95, include_review: bool = True) -> dict[str, Any]:
    """Percentile CIs for three rates and three contrasts in each model.

    Complete triplets only. All models and repetitions of a claim are resampled
    together. ``n_bootstrap_valid`` exposes draws with absent model populations.
    Empty input returns empty tables. Fewer than 2 claim clusters returns null CIs.
    """
    return _bootstrap(prepare_paired(rows, include_review=include_review),
                      n_bootstrap=n_bootstrap, seed=seed, level=level)


def analyze_baseline(rows: Records, *, n_bootstrap: int = 2000, seed: int = 42,
                     include_review: bool = True) -> dict[str, Any]:
    """Return reproducible, JSON-safe descriptive and paired baseline statistics.

    Keys: metadata, rates_by_confidence/domain/difficulty, paired (exclusion
    report), paired_rates_by_confidence, cochran_q, mcnemar, bootstrap. No file I/O
    or provider access occurs here. ``json.dumps(result, allow_nan=False)`` works.
    Filtering review flags is a sensitivity analysis, not human validation.
    """
    frame = evaluated_frame(rows)
    paired = _prepare_paired(frame, include_review)
    selected = frame if include_review else frame[~frame["needs_human_review"]]
    complete_keys = set(paired.complete[BLOCK_COLUMNS].itertuples(index=False, name=None))
    complete_mask = [tuple(row) in complete_keys for row in frame[BLOCK_COLUMNS].itertuples(index=False, name=None)]
    paired_rows = frame.loc[complete_mask]
    return {"metadata": {"n_observed_responses": len(frame), "n_selected_responses": len(selected),
                         "n_claims": int(frame["claim_id"].nunique()),
                         "n_models": int(frame["model"].nunique()), "seed": seed,
                         "needs_human_review": int(frame["needs_human_review"].sum()),
                         "include_review": include_review, "labels": "provisional unless human validated",
                         "paired_tests_repetition_policy": "separate test per repetition; never independent pooling",
                         "bootstrap_interval": "pointwise percentile; empirical degeneracy is not equivalence",
                         "multiplicity": "Holm on all pairwise tests per model/outcome; Q tests unadjusted"},
            "rates_by_confidence": _metric_table(selected, ["model", "confidence"]),
            "rates_by_domain": _metric_table(selected, ["model", "domain", "confidence"]),
            "rates_by_difficulty": _metric_table(selected, ["model", "difficulty", "confidence"]),
            "paired_rates_by_confidence": _metric_table(paired_rows, ["model", "confidence"]),
            "paired": paired.report, **paired_tests(paired),
            "bootstrap": _bootstrap(paired, n_bootstrap=n_bootstrap, seed=seed, level=0.95)}
