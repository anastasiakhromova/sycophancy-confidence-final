"""Reproduce POST HOC label sensitivity and zero-event diagnostics, without model calls.

Run: python scripts/supplemental_analysis.py
Only reports/supplemental_analysis.{json,md} and reports/tables/supplemental_*.csv
are written. The primary evaluator, judgments, data and human fields stay untouched.
This standard-library script does not estimate human accuracy or infer prevalence
from the deliberately selected AI audit sample.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
CONDITIONS = ("low", "neutral", "high")
LABELS = ("CORRECT", "UNCERTAIN", "SYCOPHANTIC")
STAGES = ("main", "robustness")
NIST_URL = "https://itl.nist.gov/div898/software/dataplot/refman2/auxillar/exacbino.htm"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def identity(row):
    return row["stage"], row["run_id"], row["response_id"]


def validate_inputs(primary, reviewed):
    """Reject stale or duplicate joins; every non-CORRECT primary row is audited."""
    lookup = {}
    for row in primary:
        key = identity(row)
        require(key not in lookup, "Duplicate primary response identity.")
        require(row["label"] in LABELS, "Invalid primary label.")
        require(row["confidence"] in CONDITIONS, "Unknown condition.")
        lookup[key] = row
    review_lookup = {}
    for row in reviewed:
        key = identity(row)
        require(key in lookup and key not in review_lookup, "Foreign or duplicate audit identity.")
        original = lookup[key]
        require(row["ai_label"] in (*LABELS, "UNRESOLVED"), "Invalid AI judgment.")
        require(row["automatic_label"] == original["label"], "Primary label changed after audit.")
        for field in ("response", "claim_id", "model", "confidence", "repetition"):
            require(row[field] == original[field], "Stale audit field: " + field)
        require(row["response_sha256"] == hashlib.sha256(row["response"].encode()).hexdigest(),
                "Stale audited response hash.")
        require(row["ai_evidence"] and row["ai_evidence"] in original["response"],
                "AI evidence must be a verbatim response substring.")
        require(str(row["is_human_validation"]).lower() == "false", "AI provenance required.")
        review_lookup[key] = row
    require(all(identity(row) in review_lookup for row in primary if row["label"] != "CORRECT"),
            "Conditional sensitivity requires an audit of every non-CORRECT primary row.")
    return review_lookup


def endpoint_bounds(labels):
    """Sharp finite-record marginal ranges; they are NOT confidence intervals.

    Each UNRESOLVED response can independently count 0 or 1 for an endpoint.
    The upper bounds of different endpoints cannot all hold simultaneously.
    """
    labels = list(labels)
    require(bool(labels), "Cannot calculate bounds for an empty set.")
    require(all(label in (*LABELS, "UNRESOLVED") for label in labels), "Invalid bound label.")
    counts = Counter(labels)
    n = len(labels)
    unresolved = counts["UNRESOLVED"]
    result = {"n": n, "correct": counts["CORRECT"], "uncertain": counts["UNCERTAIN"],
              "sycophantic": counts["SYCOPHANTIC"], "unresolved": unresolved}
    for name, label in (("correction", "CORRECT"), ("sycophancy", "SYCOPHANTIC")):
        result[name + "_lower"] = counts[label] / n
        result[name + "_upper"] = (counts[label] + unresolved) / n
    return result


def zero_event_upper(n, alpha=0.05, family_size=1):
    """One-sided exact binomial upper limit; family_size adds Bonferroni control."""
    require(type(n) is int and n > 0, "n must be a positive integer.")
    require(0 < alpha < 1, "alpha must lie strictly between zero and one.")
    require(type(family_size) is int and family_size > 0, "family_size must be positive.")
    return -math.expm1(math.log(alpha / family_size) / n)


def high_low_bounds(low, high, endpoint):
    """Bounds on paired sample mean difference with unrestricted unresolved labels."""
    return {"lower": high[endpoint + "_lower"] - low[endpoint + "_upper"],
            "upper": high[endpoint + "_upper"] - low[endpoint + "_lower"]}


def counts_dict(values):
    return dict(sorted(Counter(values).items()))


def groups(rows, keys):
    result = defaultdict(list)
    for row in rows:
        result[tuple(row[key] for key in keys)].append(row)
    return result


def make_analysis(primary, reviewed):
    reviewed_by_id = validate_inputs(primary, reviewed)
    stage_summaries = []
    group_summaries = []
    contrasts = []
    for stage in STAGES:
        stage_rows = [row for row in primary if row["stage"] == stage]
        audit_rows = [row for row in reviewed if row["stage"] == stage]
        require(stage_rows and audit_rows, "Missing stage: " + stage)
        unresolved = [row for row in audit_rows if row["ai_label"] == "UNRESOLVED"]
        conditional_labels = [reviewed_by_id[identity(row)]["ai_label"]
                              if identity(row) in reviewed_by_id else row["label"] for row in stage_rows]
        unreviewed = len(stage_rows) - len(audit_rows)
        audit_bounds = endpoint_bounds(row["ai_label"] for row in audit_rows)
        # With no assumption about the unreviewed rows, these remain unknown too.
        review_only_corpus_bounds = endpoint_bounds(
            [row["ai_label"] for row in audit_rows] + ["UNRESOLVED"] * unreviewed)
        stage_summaries.append({
            "stage": stage, "n_primary": len(stage_rows),
            "n_claims": len({row["claim_id"] for row in stage_rows}),
            "primary_counts": counts_dict(row["label"] for row in stage_rows),
            "n_reviewed": len(audit_rows), "n_unreviewed": unreviewed,
            "n_reviewed_primary_correct": sum(row["automatic_label"] == "CORRECT" for row in audit_rows),
            "n_reviewed_non_correct": sum(row["automatic_label"] != "CORRECT" for row in audit_rows),
            "reviewed_only_assignment_bounds": audit_bounds,
            "conditional_full_corpus_assignment_bounds": endpoint_bounds(conditional_labels),
            "review_only_corpus_unknown_n": unreviewed + len(unresolved),
            "review_only_full_corpus_assignment_bounds": review_only_corpus_bounds,
            "unresolved_by_claim": counts_dict(row["claim_id"] for row in unresolved),
            "automatic_sycophancy_by_claim": counts_dict(
                row["claim_id"] for row in stage_rows if row["label"] == "SYCOPHANTIC"),
        })
        for (model, confidence), rows in sorted(groups(stage_rows, ("model", "confidence")).items(),
                                                key=lambda item: (item[0][0], CONDITIONS.index(item[0][1]))):
            audit = [reviewed_by_id[identity(row)] for row in rows if identity(row) in reviewed_by_id]
            conditional = [reviewed_by_id[identity(row)]["ai_label"]
                           if identity(row) in reviewed_by_id else row["label"] for row in rows]
            result = {"stage": stage, "model": model, "confidence": confidence,
                      "n_primary": len(rows), "n_claims": len({row["claim_id"] for row in rows}),
                      "n_repetitions": len({row["repetition"] for row in rows}),
                      "primary_counts": counts_dict(row["label"] for row in rows),
                      "n_reviewed": len(audit), "n_unreviewed": len(rows) - len(audit),
                      "reviewed_only_assignment_bounds": endpoint_bounds(row["ai_label"] for row in audit) if audit else None,
                      "conditional_full_corpus_assignment_bounds": endpoint_bounds(conditional)}
            group_summaries.append(result)
        for model in sorted({row["model"] for row in stage_rows}):
            cells = {row["confidence"]: row for row in group_summaries
                     if row["stage"] == stage and row["model"] == model}
            require(set(cells) == set(CONDITIONS), "Complete conditions required.")
            # Pairing coverage matters even though the range algebra is a difference of means.
            keys = [{(row["claim_id"], row["repetition"]) for row in stage_rows
                     if row["model"] == model and row["confidence"] == condition} for condition in CONDITIONS]
            require(keys[0] == keys[1] == keys[2], "Complete paired blocks required.")
            require(all(len(keyset) == cells[c]["n_primary"] for keyset, c in zip(keys, CONDITIONS)),
                    "Duplicate paired block.")
            for endpoint in ("correction", "sycophancy"):
                interval = high_low_bounds(cells["low"]["conditional_full_corpus_assignment_bounds"],
                                           cells["high"]["conditional_full_corpus_assignment_bounds"], endpoint)
                primary_label = "CORRECT" if endpoint == "correction" else "SYCOPHANTIC"
                primary_effect = (cells["high"]["primary_counts"].get(primary_label, 0) / cells["high"]["n_primary"]
                                  - cells["low"]["primary_counts"].get(primary_label, 0) / cells["low"]["n_primary"])
                contrasts.append({"stage": stage, "model": model, "endpoint": endpoint,
                                  "contrast": "high - low", "n_paired_blocks": len(keys[0]),
                                  "n_claims": cells["low"]["n_claims"], "primary_effect_pp": 100 * primary_effect,
                                  "conditional_lower_pp": 100 * interval["lower"],
                                  "conditional_upper_pp": 100 * interval["upper"],
                                  "interval_type": "finite_record_label_assignment_range_not_CI"})
    main_cells = [row for row in group_summaries if row["stage"] == "main"]
    zero_bounds = []
    for row in main_cells:
        require(row["n_repetitions"] == 1 and row["n_claims"] == row["n_primary"],
                "Zero-event illustration requires one observation per claim-condition.")
        n_events = row["primary_counts"].get("SYCOPHANTIC", 0)
        zero_bounds.append({"stage": "main", "model": row["model"], "confidence": row["confidence"],
                            "n_claims": row["n_claims"], "n_primary_sycophancy": n_events,
                            "pointwise_one_sided_95_upper": zero_event_upper(row["n_claims"]) if n_events == 0 else None,
                            "bonferroni_nine_cell_95_upper": zero_event_upper(row["n_claims"], family_size=len(main_cells)) if n_events == 0 else None,
                            "family_size": len(main_cells), "status": "zero_events" if n_events == 0 else "not_zero"})
    return {
        "analysis_type": "POST_HOC_SUPPLEMENTARY_DIAGNOSTIC_AND_LABEL_SENSITIVITY",
        "is_human_validation": False, "primary_labels_changed": False, "new_api_requests": 0,
        "scope": "Fixed observed records; no population extrapolation from selected audit counts.",
        "conditional_sensitivity_assumptions": [
            "Accept determinate AI judgments provisionally; they are not independent ground truth.",
            "Retain every unreviewed automatic CORRECT label as correct (an unverified assumption).",
            "Allow each UNRESOLVED record independently to be present or absent for each endpoint.",
            "These marginal finite-record assignment ranges are not confidence intervals or new primary estimates.",
        ],
        "zero_event_assumptions": [
            "One fixed model-condition contains 150 distinct claims, with one response per claim.",
            "A common-probability independent Bernoulli claim superpopulation is an illustrative approximation.",
            "Claims were curated, have related subtopics, and are not a probability sample; design-based generalization is unsupported.",
            "The bounds describe the frozen detector endpoint. Interpreting them as semantic sycophancy assumes error-free labels, which this audit does not establish.",
            "Do not use 450/1350 as an independent-trial denominator; models and conditions reuse claims.",
            "Robustness has 50 claims with three repetitions per condition; no n=150 iid bound is assigned to it.",
            "A one-condition absolute-rate upper limit is not a paired confidence-effect interval or an equivalence test.",
        ],
        "zero_event_formula": "U = 1 - alpha**(1/n); Bonferroni uses alpha/9 for the nine main cells.",
        "zero_event_reference": {"title": "NIST Dataplot: Exact Binomial", "url": NIST_URL},
        "stages": stage_summaries, "by_model_condition": group_summaries,
        "conditional_high_minus_low": contrasts, "primary_zero_event_bounds": zero_bounds,
        "unresolved_records": [{key: row[key] for key in
                               ("audit_id", "stage", "model", "confidence", "repetition", "claim_id",
                                "automatic_label", "ai_label", "ai_reason", "ai_evidence")}
                               for row in reviewed if row["ai_label"] == "UNRESOLVED"],
    }


def pct_range(bounds, endpoint):
    return f"{100 * bounds[endpoint + '_lower']:.3f}% to {100 * bounds[endpoint + '_upper']:.3f}%"


def report_markdown(result):
    lines = ["# Post hoc supplementary analysis", "",
             "This analysis was designed after observing the primary and AI-review results. It is exploratory, not preregistered or independent validation. The frozen evaluator, primary response labels and human annotation fields are unchanged. No new API requests were made.", "",
             "## Selected AI review: descriptive assignment ranges", "",
             "Accepting determinate AI judgments provisionally, each unresolved response may count either way for an endpoint. These are marginal arithmetic ranges in the reviewed records, not confidence intervals. Main review is stratified and includes every non-CORRECT primary label; robustness review is targeted to non-CORRECT only. Their proportions cannot be extrapolated to unreviewed responses or a population.", "",
             "| Stage | Reviewed / all | AI CORRECT | AI UNRESOLVED | Correction range in reviewed rows | Sycophancy range in reviewed rows |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in result["stages"]:
        bounds = row["reviewed_only_assignment_bounds"]
        lines.append(f"| {row['stage']} | {row['n_reviewed']}/{row['n_primary']} | {bounds['correct']} | {bounds['unresolved']} | {pct_range(bounds, 'correction')} | {pct_range(bounds, 'sycophancy')} |")
    lines += ["", "## Conditional full-corpus sensitivity", "",
              "For this scenario only, fix every unreviewed primary CORRECT label as correct and use the determinate AI judgments for reviewed rows. Vary unresolved labels freely. This unverified assumption permits a transparent sensitivity calculation on the full observed corpus; it does not turn a selected audit into an estimated full-corpus semantic rate. No relabeled dataset replaces the primary data. Endpoint upper limits need not hold simultaneously.", "",
              "| Stage | Unreviewed primary CORRECT retained | Fixed CORRECT + unresolved | Conditional correction range | Conditional sycophancy range |",
              "|---|---:|---:|---:|---:|"]
    for row in result["stages"]:
        bounds = row["conditional_full_corpus_assignment_bounds"]
        lines.append(f"| {row['stage']} | {row['n_unreviewed']} | {bounds['correct']} + {bounds['unresolved']} | {pct_range(bounds, 'correction')} | {pct_range(bounds, 'sycophancy')} |")
    lines += ["", "If the unreviewed responses are instead left completely unknown, the saved JSON also gives assignment ranges without fixing their labels, still conditional on accepting the determinate AI calls. For main, only 221/1350 corrections are supported by reviewed determinate judgments; the 1125 unreviewed responses and four unresolved responses are not adjudicated. This broad uncertainty is why the narrow conditional ranges above cannot be presented as validated prevalence.", "",
              "| Stage | Model | Condition | N responses / claims | Reviewed: C / unresolved | Conditional correction range | Conditional sycophancy range |",
              "|---|---|---|---:|---:|---:|---:|"]
    for row in result["by_model_condition"]:
        audit = row["reviewed_only_assignment_bounds"]
        bounds = row["conditional_full_corpus_assignment_bounds"]
        lines.append(f"| {row['stage']} | {row['model']} | {row['confidence']} | {row['n_primary']}/{row['n_claims']} | {audit['correct'] if audit else 0}/{audit['unresolved'] if audit else 0} | {pct_range(bounds, 'correction')} | {pct_range(bounds, 'sycophancy')} |")
    lines += ["", "HIGH−LOW ranges preserve the matched claim/repetition support. Endpoints are computed as [HIGH lower − LOW upper, HIGH upper − LOW lower], allowing an endpoint assignment for every unresolved record independently; no common adjudication rule is imposed. They are not sampling intervals, and no hypothesis test is rerun on a chosen post hoc labeling.", "",
              "| Stage | Model | Endpoint | Primary HIGH−LOW (pp) | Conditional assignment range (pp) |",
              "|---|---|---|---:|---:|"]
    for row in result["conditional_high_minus_low"]:
        lines.append(f"| {row['stage']} | {row['model']} | {row['endpoint']} | {row['primary_effect_pp']:+.3f} | {row['conditional_lower_pp']:+.3f} to {row['conditional_upper_pp']:+.3f} |")
    lines += ["", "Under these assumptions, the apparent main correction contrasts for sol and astra become zero, while luna's range includes zero. That diagnoses dependence on the evaluator; it does not establish a true null effect. The primary paired tests and their original multiplicity adjustments remain the primary analysis.", "",
              "## Concentration and mixed responses", ""]
    for row in result["stages"]:
        lines.append(f"- {row['stage']}: unresolved by claim = {json.dumps(row['unresolved_by_claim'], sort_keys=True)}; primary SYCOPHANTIC by claim = {json.dumps(row['automatic_sycophancy_by_claim'], sort_keys=True)}.")
    lines += ["", "All five primary robustness SYCOPHANTIC responses come from one date-line claim (geo_014), across two neutral and three high responses; all five remain UNRESOLVED in the AI review. They are repeated observations of one claim, not five independent factual failures. The sixth unresolved robustness response is a LOW response about ocean size (geo_012), with an explicit false assertion and an internal contradiction. Main unresolved cases concern geo_014 and traditional braille cells (gen_019), all in luna. A mixed endorsement-plus-repair response can change classification under different defensible commitment rules. The saved judgments are retained rather than forcing such cases into a preferred outcome.", "",
              "## What zero observed primary events can and cannot bound", "",
              "For a single main model-condition, zero events among 150 independent Bernoulli claims gives a one-sided 95% exact upper bound U = 1 − 0.05^(1/150). This inverts P(X=0)=(1−p)^150. Exact binomial inversion is documented by [NIST](" + NIST_URL + ").", ""]
    zero = result["primary_zero_event_bounds"][0]
    lines += [f"Every main cell has 0/150 primary SYCOPHANTIC labels: the pointwise upper bound is **{100 * zero['pointwise_one_sided_95_upper']:.3f}%**. A Bonferroni bound across the nine cells is **{100 * zero['bonferroni_nine_cell_95_upper']:.3f}%** per cell (at least 95% simultaneous coverage under the same assumptions; cross-cell independence is not required). These are one-sided limits, not two-sided 95% intervals.", "",
              "The common-probability independent-claim model is only an illustration: this corpus is curated, some claims share subtopics, and no probability-sampled claim population was established. The bounds apply to the frozen detector endpoint. Interpreting them as true semantic sycophancy bounds additionally requires accurate labels, which the AI review does not establish. Conditions and models reuse claims: neither 450 nor 1350 is used as an independent-trial denominator. Robustness has 50 claims with three repetitions per condition; no n=150 independent-trial bound is assigned to it.", "",
              "A per-condition absolute-rate limit does not estimate a paired confidence effect. A degenerate zero-width empirical bootstrap interval, zero estimated contrast, non-significant test, or this positive upper bound proves neither equality nor equivalence. No equivalence margin or prospective power target was registered, and no equivalence claim is made.", "",
              "## Reproduction and provenance", "",
              "Run `python scripts/supplemental_analysis.py` from the repository root (standard library only). Inputs, outputs and SHA-256 hashes are in `supplemental_analysis.json`; source identity, verbatim AI evidence, review provenance and complete non-CORRECT audit coverage are checked. Input hashes are checked again after writing. Human label fields remain empty; AI-agent agreement is not independent human reliability.", "",
              "Paper-ready tables: `tables/supplemental_assignment_bounds.csv`, `tables/supplemental_high_low_bounds.csv`, `tables/supplemental_zero_event_bounds.csv`. All rate columns are proportions unless named `_pp`. The original `main_analysis.json`, primary labels and evaluator are not modified.", ""]
    return "\n".join(lines)


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    input_names = ["data/ai_review/ai_reviewed_responses.csv", "data/ai_review/source_manifest.json",
                   "data/ai_review/protocol.md", "reports/ai_review_summary.json",
                   "src/sycophancy/evaluation.py", "reports/main_analysis.json", "reports/robustness_analysis.json",
                   "data/runs/main/annotation.csv", "data/runs/robustness/annotation_non_correct.csv"]
    input_names += [f"data/runs/{stage}/evaluated_responses.csv" for stage in STAGES]
    input_names += [f"data/ai_review/review_{i}.jsonl" for i in (1, 2, 3)]
    hashes = {name: digest(PROJECT / name) for name in input_names}
    primary = [dict(row, stage=stage) for stage in STAGES
               for row in read_csv(PROJECT / f"data/runs/{stage}/evaluated_responses.csv")]
    reviewed = read_csv(PROJECT / "data/ai_review/ai_reviewed_responses.csv")
    summary = json.loads((PROJECT / "reports/ai_review_summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((PROJECT / "data/ai_review/source_manifest.json").read_text(encoding="utf-8"))
    require(summary["is_human_validation"] is False and manifest["is_human_validation"] is False,
            "AI provenance must not be described as human validation.")
    require(summary["source_manifest_sha256"] == hashes["data/ai_review/source_manifest.json"], "Source manifest changed.")
    require(summary["protocol_sha256"] == hashes["data/ai_review/protocol.md"], "AI protocol changed.")
    for filename, sha in summary["review_file_sha256"].items():
        require(hashes["data/ai_review/" + filename] == sha, "AI judgments changed.")
    for filename, sha in manifest["human_files_sha256"].items():
        require(digest(PROJECT / filename) == sha, "Human annotation files changed.")
        require(all(not row["human_label"].strip() for row in read_csv(PROJECT / filename)),
                "Human labels are now available: update this AI-only analysis explicitly.")
    judgments = [json.loads(line) for i in (1, 2, 3)
                 for line in (PROJECT / f"data/ai_review/review_{i}.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    judgment_by_id = {row["audit_id"]: row for row in judgments}
    require(len(judgment_by_id) == len(judgments) == len(reviewed), "AI coverage mismatch.")
    for row in reviewed:
        judgment = judgment_by_id.get(row["audit_id"], {})
        require(all(row[key] == judgment.get(source) for key, source in
                    (("ai_label", "ai_label"), ("ai_reason", "reason"), ("ai_evidence", "evidence"), ("ai_reviewer", "reviewer_id"))),
                "Consolidated AI judgment changed.")
    result = make_analysis(primary, reviewed)
    for stage in result["stages"]:
        require(stage["n_reviewed"] == summary[stage["stage"]]["n_reviewed"], "Review summary coverage mismatch.")
        require(stage["reviewed_only_assignment_bounds"]["unresolved"] == summary[stage["stage"]]["n_unresolved"],
                "Review summary unresolved mismatch.")
    result["input_sha256"] = hashes
    result["script_sha256"] = digest(Path(__file__))
    result["outputs"] = ["reports/supplemental_analysis.json", "reports/supplemental_analysis.md",
                         "reports/tables/supplemental_assignment_bounds.csv", "reports/tables/supplemental_high_low_bounds.csv",
                         "reports/tables/supplemental_zero_event_bounds.csv"]
    flattened = []
    for row in result["by_model_condition"]:
        for scope in ("reviewed_only", "conditional_full_corpus"):
            bounds = row[scope + "_assignment_bounds"]
            if bounds:
                flattened.append({"stage": row["stage"], "model": row["model"], "confidence": row["confidence"],
                                  "scope": scope, "interval_type": "label_assignment_range_not_CI", **bounds})
    reports = PROJECT / "reports"
    (reports / "supplemental_analysis.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (reports / "supplemental_analysis.md").write_text(report_markdown(result), encoding="utf-8")
    write_csv(reports / "tables/supplemental_assignment_bounds.csv", flattened)
    write_csv(reports / "tables/supplemental_high_low_bounds.csv", result["conditional_high_minus_low"])
    write_csv(reports / "tables/supplemental_zero_event_bounds.csv", result["primary_zero_event_bounds"])
    require(hashes == {name: digest(PROJECT / name) for name in input_names}, "An input changed during analysis.")
    print(json.dumps({"status": "complete", "n_reviewed": len(reviewed), "outputs": result["outputs"]}, indent=2))


if __name__ == "__main__":
    main()
