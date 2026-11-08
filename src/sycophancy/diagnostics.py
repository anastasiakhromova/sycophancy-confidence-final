"""Validate and display optional post-hoc AI observations, never primary labels.

``load_ai_diagnostics(path, rows, collection)`` accepts evaluated primary record
dictionaries and the original collection manifest. Missing files return None;
present but stale, incomplete or incorrectly attributed audits raise ValueError.
``render_ai_diagnostics(payload)`` returns Markdown blocks for the validated
payload (or an empty list for None). Neither function writes any files.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

_LABELS = ("CORRECT", "UNCERTAIN", "SYCOPHANTIC")
_ASSESSMENTS = (*_LABELS, "unresolved")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(f"AI diagnostics: {message}")


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _key(row: Mapping) -> tuple[str, str]:
    _require(_text(row.get("run_id")) and _text(row.get("response_id")),
             "nonempty run_id and response_id are required")
    return row["run_id"], row["response_id"]


def _counts(values, categories):
    counts = Counter(values)
    return {category: counts[category] for category in categories}


def load_ai_diagnostics(
    path: str | Path | None,
    rows: Sequence[Mapping[str, object]],
    collection: Mapping[str, object],
) -> dict | None:
    """Return an audit bound to the complete current collection, or None.

    ``rows`` must contain ``label`` from the frozen automatic evaluator, the raw
    ``response``, and run/response/model/claim/confidence identity. ``collection``
    is the original manifest with model_runs[*].specification.total_responses
    and frozen evaluator_sha256/aliases_sha256. Scope totals are checked; label
    and assessment counts are rebuilt from validated rows/cases, ignoring any
    supplied summary. The input dictionaries and primary labels are untouched.
    """
    if path is None or not Path(path).exists():
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("AI diagnostics: cannot read a valid JSON audit") from exc
    _require(isinstance(payload, dict), "audit must be a JSON object")
    _require(payload.get("audit_type") == "post_hoc_ai_review", "audit_type must be post_hoc_ai_review")
    _require(payload.get("is_human_validation") is False, "audit must explicitly state is_human_validation=false")
    _require(isinstance(collection, Mapping), "original collection manifest is required")
    for field in ("evaluator_sha256", "aliases_sha256"):
        frozen = collection.get(field)
        _require(isinstance(frozen, str) and re.fullmatch(r"[0-9a-f]{64}", frozen) is not None,
                 f"collection lacks a valid frozen {field}")
        _require(payload.get(field) == frozen, f"frozen {field} mismatch")
    if collection.get("evaluator_version") is not None:
        _require(payload.get("evaluator_version") == collection["evaluator_version"], "evaluator_version mismatch")
    try:
        timestamp = datetime.fromisoformat(payload["timestamp_utc"])
        _require(timestamp.tzinfo is not None, "timestamp_utc must include a timezone")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("AI diagnostics: a valid timezone-aware timestamp_utc is required") from exc

    model_runs = collection.get("model_runs")
    _require(isinstance(model_runs, list) and bool(model_runs), "collection model_runs are required for complete scope")
    expected_by_model = {}
    for run in model_runs:
        _require(isinstance(run, Mapping), "invalid collection model run")
        model = run.get("model")
        spec = run.get("specification")
        _require(_text(model) and model not in expected_by_model and isinstance(spec, Mapping),
                 "invalid or duplicate collection model run")
        count = spec.get("total_responses")
        _require(type(count) is int and count >= 0, "invalid expected response total")
        expected_by_model[model] = count

    current = {}
    response_ids = set()
    for row in rows:
        _require(isinstance(row, Mapping), "evaluated rows must be dictionaries")
        key = _key(row)
        _require(key not in current and key[1] not in response_ids, "duplicate current response identity")
        _require(row.get("label") in _LABELS, "current automatic label is invalid")
        _require(_text(row.get("response")), "current raw response must be nonempty")
        _require(_text(row.get("model")) and _text(row.get("claim_id"))
                 and row.get("confidence") in {"low", "neutral", "high"}, "invalid current response metadata")
        current[key] = row
        response_ids.add(key[1])
    _require(Counter(r["model"] for r in current.values()) == Counter(expected_by_model),
             "current rows do not cover the complete collection by model")
    expected = {key: row for key, row in current.items() if row["label"] != "CORRECT"}
    cases = payload.get("cases")
    _require(isinstance(cases, list), "cases must be a list")
    seen = set()
    seen_response_ids = set()
    for case in cases:
        _require(isinstance(case, dict), "each diagnostic case must be an object")
        key = _key(case)
        _require(key not in seen and key[1] not in seen_response_ids, "duplicate audit response identity")
        seen.add(key)
        seen_response_ids.add(key[1])
        _require(key in expected, "case identity is stale or outside the non-CORRECT scope")
        row = expected[key]
        for field in ("model", "claim_id", "confidence"):
            _require(case.get(field) == row[field], f"case {field} mismatch for {key[1]}")
        _require(case.get("automatic_label") == row["label"], f"automatic_label mismatch for {key[1]}")
        digest = hashlib.sha256(row["response"].encode("utf-8")).hexdigest()
        _require(case.get("response_sha256") == digest, f"raw response SHA256 mismatch for {key[1]}")
        _require(_text(case.get("evidence")) and case["evidence"] in row["response"],
                 f"evidence must be a verbatim raw-response substring for {key[1]}")
        _require(case.get("ai_assessment") in _ASSESSMENTS, f"invalid ai_assessment for {key[1]}")
        _require(_text(case.get("reason")), f"a reason is required for {key[1]}")
        if "diagnostic_category" in case:
            _require(_text(case["diagnostic_category"]), f"invalid diagnostic_category for {key[1]}")
    _require(seen == set(expected), "audit coverage must exactly match all non-CORRECT response identities")
    scope = payload.get("scope")
    _require(isinstance(scope, dict), "scope must be an object")
    totals = {"total_expected": sum(expected_by_model.values()), "total_available": len(current),
              "n_non_correct": len(expected), "n_audited": len(cases),
              "n_correct_not_audited": len(current) - len(cases)}
    for field, value in totals.items():
        _require(type(scope.get(field)) is int and scope[field] == value, f"scope {field} mismatch")

    # Canonical counts come from verified records, not the author's summary.
    result = deepcopy(payload)
    result["scope"] = {"population": "All non-CORRECT automatic labels in the complete main collection only",
                       **totals, "automatic_label_counts": _counts((r["label"] for r in current.values()), _LABELS),
                       "automatic_label_counts_by_model": {
                           model: _counts((r["label"] for r in current.values() if r["model"] == model), _LABELS)
                           for model in sorted(expected_by_model)}}
    result["summary"] = {
        "ai_assessment_counts": _counts((c["ai_assessment"] for c in cases), _ASSESSMENTS),
        "diagnostic_category_counts": dict(sorted(Counter(c.get("diagnostic_category", "unspecified") for c in cases).items())),
        "questionable_behavior_response_ids": [c["response_id"] for c in cases if c["ai_assessment"] != "CORRECT"],
    }
    result["audit_status"] = "complete_non_correct_scope"
    return result


def render_ai_diagnostics(diagnostics: Mapping[str, object] | None) -> list[str]:
    """Return Markdown blocks for a payload from load_ai_diagnostics; [] if absent."""
    if diagnostics is None:
        return []
    _require(diagnostics.get("audit_type") == "post_hoc_ai_review"
             and diagnostics.get("is_human_validation") is False, "renderer accepts only an explicit AI-only audit")
    scope = diagnostics["scope"]
    counts = _counts((case["ai_assessment"] for case in diagnostics["cases"]), _ASSESSMENTS)
    table = "\n".join(["| Post-hoc AI assessment | Audited responses |", "|---|---:|"] +
                      [f"| {label} | {counts[label]} |" for label in _ASSESSMENTS])
    return [
        "**Initial post-hoc AI diagnostic review — not human validation.** These assistant judgments are observations, not ground truth; the primary automatic labels and analyses remain unchanged.",
        f"The audit reviewed all {scope['n_non_correct']} non-CORRECT automatic labels among {scope['total_available']} main responses. It considered {counts['CORRECT']} responses to contain factual corrections missed by the primary rules and left {counts['unresolved']} unresolved; these are AI assessments within the selected subset.",
        table,
        f"The {scope['n_correct_not_audited']} automatic CORRECT responses were not audited in this initial non-CORRECT-only review. This selected audit does not estimate evaluator accuracy or sensitivity and must not populate human annotation fields. Unresolved cases require human adjudication, including any mixture of factual repair and misleading agreement or scope changes.",
        "[Full post-hoc AI diagnostic audit](evaluator_diagnostics.md) contains per-response reasons, short verbatim evidence, and provenance hashes.",
    ]
