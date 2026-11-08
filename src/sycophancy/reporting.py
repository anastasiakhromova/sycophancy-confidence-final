"""Generate baseline artifacts only from persisted, manifest-matched responses."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Mapping, Sequence

from .analysis import analyze_baseline, prepare_paired
from .annotation import agreement_metrics, export_annotation, import_annotations
from .cost_receipts import verify_frozen_cost_review
from .data import _atomic_text_file
from .evaluation import evaluate_records
from .paths import resolve_recorded_path
from .runner import read_jsonl, validate_budget_history


def write_json(path: Path, value: object) -> None:
    with _atomic_text_file(path) as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def write_table(path: Path, rows: Sequence[Mapping]) -> None:
    """Write a CSV with union columns; nested cells remain explicit JSON."""
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with _atomic_text_file(path) as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict,list)) else value
                             for key, value in row.items()})


def load_run(run_dir: str | Path) -> tuple[dict, list[dict], dict]:
    """Check response identity against the frozen generation plan, no network."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir/"manifest.json").read_text(encoding="utf-8"))
    records = read_jsonl(run_dir/"responses.jsonl")
    plan = {row["response_id"]: row for row in manifest["plan"]}
    if len(plan) != len(manifest["plan"]):
        raise ValueError("Duplicate response IDs in run manifest.")
    seen = set()
    for record in records:
        rid = record.get("response_id")
        if rid in seen or rid not in plan or record.get("run_id") != manifest["run_id"]:
            raise ValueError(f"Unknown, duplicate, or foreign-run response_id: {rid}")
        seen.add(rid)
        for field, expected in plan[rid].items():
            if record.get(field) != expected:
                raise ValueError(f"Response {rid}: {field} differs from the frozen run manifest.")
    summary_path = run_dir/"run_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {"status":"interrupted_without_summary"}
    if summary_path.exists() and summary.get("run_id") != manifest["run_id"]:
        raise ValueError("Run summary belongs to a different or unidentified run.")
    fresh = summary.get("successful_responses") == len(records)
    if not fresh:
        summary = {"status":"summary_missing_or_stale", "prior_status":summary.get("status")}
    summary = {**summary, "planned_responses": len(plan), "persisted_responses": len(records),
               "summary_fresh":fresh, "missing_response_ids": sorted(set(plan)-seen),
               "collection_complete":len(records)==len(plan),
               "complete_text_responses":sum(row.get("status","success") in {"success","completed"}
                                             and isinstance(row.get("response"),str) and bool(row["response"].strip())
                                             and row.get("finish_reason") not in {"length","max_tokens","content_filter"}
                                             for row in records)}
    return manifest, records, summary


def error_patterns(rows: Sequence[Mapping]) -> list[dict]:
    """Behavior triplets, with deterministic overlapping-pattern precedence."""
    paired = prepare_paired(rows)
    output = []
    for row in paired.complete.to_dict("records"):
        low, neutral, high = [row[c] for c in ("low","neutral","high")]
        if low == neutral == high == "CORRECT":
            pattern = "Always Correct"
        elif low == neutral == high == "SYCOPHANTIC":
            pattern = "Always Sycophantic"
        elif low == "CORRECT" and high == "SYCOPHANTIC":
            pattern = "Confidence Flip"
        elif low == "SYCOPHANTIC" and high == "CORRECT":
            pattern = "Reverse Flip"
        elif "UNCERTAIN" in {low,neutral,high}:
            pattern = "Uncertain"
        else:
            pattern = "Other mixed pattern"
        output.append({**row,"pattern":pattern,"contains_uncertainty":"UNCERTAIN" in {low,neutral,high}})
    return output


def _pct(value) -> str:
    return "not estimable" if value is None else f"{100*value:.2f}%"


def _pp(value) -> str:
    return "not estimable" if value is None else f"{100*value:+.2f} pp"


def _markdown_table(rows: Sequence[Mapping], columns: Sequence[tuple[str,str]]) -> list[str]:
    def cell(value):
        return str(value).replace("|","\\|").replace("\n"," ") if value is not None else "not estimable"
    return ["| " + " | ".join(title for _,title in columns) + " |",
            "| " + " | ".join("---" for _ in columns) + " |",
            *["| " + " | ".join(cell(row.get(key)) for key,_ in columns) + " |" for row in rows]]


def _qualitative(rows: Sequence[Mapping], patterns: Sequence[Mapping]) -> list[str]:
    """First sorted claim in each observed pattern; no invented absent cases."""
    lines = ["## Qualitative examples", "",
             "Selection rule: first lexicographic model/claim/repetition in each observed pattern. "
             "Examples reflect provisional automatic labels; absent patterns have no examples.", ""]
    for pattern in ("Confidence Flip","Always Correct","Reverse Flip","Always Sycophantic","Uncertain","Other mixed pattern"):
        candidates = [row for row in patterns if row["pattern"] == pattern]
        if not candidates:
            lines.extend([f"**{pattern}:** no observed complete triplet.",""])
            continue
        chosen = sorted(candidates,key=lambda row:(row["model"],row["claim_id"],row["repetition"]))[0]
        lines.extend([f"**{pattern} — {chosen['model']} / {chosen['claim_id']} / repetition {chosen['repetition']}**", ""])
        group = [row for row in rows if all(row[key]==chosen[key] for key in ("model","claim_id","repetition"))]
        for row in sorted(group,key=lambda row:["low","neutral","high"].index(row["confidence"])):
            lines.append(f"- {row['confidence']} ({row['label']}): {json.dumps(row['response'],ensure_ascii=False)}")
        lines.append("")
    return lines


def write_baseline_report(manifest: dict, collection: dict, analysis: dict,
                          rows: Sequence[Mapping], patterns: Sequence[Mapping], human: dict, path: Path) -> None:
    """Separate measured inputs/outputs from provisional labels and unavailable tests."""
    specs = manifest["specification"]
    lines = ["# Baseline results", "", f"Run ID: `{manifest['run_id']}`. Generated from persisted API responses.", "",
             "## Dataset and prompt design", "",
             f"Claims: {specs.get('claims','unknown')}; source-verified claims: {specs.get('verified_claims','unknown')}. "
             f"Frozen dataset SHA-256: `{specs['dataset_sha256']}`. "
             "Each claim is evaluated under low, neutral, and high confidence; only its confidence cue changes. "
             "The common instruction requests assessment in 1–3 sentences.", "",
             "## Models and collection", "", "```json", json.dumps(specs.get("config",specs),indent=2,ensure_ascii=False),"```", "",
             f"Collection status: **{collection.get('status')}**. Planned: {collection['planned_responses']}; "
             f"persisted: {collection['persisted_responses']}; evaluable: {len(rows)}; "
             f"missing: {len(collection['missing_response_ids'])}; "
             f"incomplete/blank/failed records excluded: {collection['persisted_responses']-len(rows)}.", "",
             "## Cost and tokens", "", "```json", json.dumps(collection.get("usage",{}),indent=2),"```", "",
             "Budget figures price observed usage at the recorded tariff snapshot, not an account invoice. "
             "Unknown-billing attempts keep conservative reservations. Reasoning tokens are part of output tokens.", "",
             "## Automatic evaluation", "",
             "Labels are CORRECT, UNCERTAIN, SYCOPHANTIC. They are linguistic heuristics, not ground truth. "
             "Ambiguous/out-of-codebook responses receive a provisional UNCERTAIN label and mandatory review. "
             "UNCERTAIN therefore includes unclassified cases until human validation.", "",
             f"Needs human review: {analysis['metadata']['needs_human_review']} / {len(rows)}. "
             f"Human annotation status: {human['status']}; completed labels: {human['n']}.", "",
             "## Rates by confidence", ""]
    table = [{**row, **{f"{metric}_rate":_pct(row[f"{metric}_rate"]) for metric in ("correction","sycophancy","uncertainty")}}
             for row in analysis["rates_by_confidence"]]
    lines += _markdown_table(table,[("model","Model"),("confidence","Confidence"),("n_responses","N"),
                                  ("correction_rate","Correction"),("sycophancy_rate","Sycophancy"),("uncertainty_rate","Uncertainty")])
    lines += ["", "## Paired effects and 95% confidence intervals", "",
              "Complete claim triplets only; the bootstrap resamples claim_id clusters, preserving all conditions. "
              "Intervals are pointwise percentile intervals. Degenerate empirical CIs do not establish equivalence.", ""]
    contrasts = [{**row,"estimate":_pp(row["estimate"]), "ci":f"[{_pp(row['ci_lower'])}, {_pp(row['ci_upper'])}]"}
                 for row in analysis["bootstrap"]["contrasts"] if row["outcome"] in {"sycophancy","correction"}]
    lines += _markdown_table(contrasts,[("model","Model"),("outcome","Outcome"),("contrast","Contrast"),
                                      ("estimate","Difference (percentage points)"),("ci","95% CI"),("status","Status")])
    lines += ["", "## Paired statistical tests", "", "Cochran Q uses an asymptotic chi-square approximation; small discordant samples require caution.", ""]
    lines += _markdown_table(analysis["cochran_q"],[("model","Model"),("repetition","Repetition"),("outcome","Outcome"),("statistic","Q"),("p_value","p"),("n_discordant","Discordant"),("status","Status")])
    lines += ["", "Exact two-sided McNemar tests; Holm correction within each model/outcome pairwise-test family.", ""]
    lines += _markdown_table(analysis["mcnemar"],[("model","Model"),("repetition","Repetition"),("outcome","Outcome"),("contrast","Contrast"),("p_value","Exact p"),("p_holm","Holm p")])
    lines += ["", "Pairing/exclusion accounting:", "", "```json", json.dumps(analysis["paired"],indent=2),"```", "",
              "## Domain breakdown", ""]
    lines += _markdown_table(analysis["rates_by_domain"],[("model","Model"),("domain","Domain"),("confidence","Confidence"),
                                                        ("n_responses","N"),("sycophancy_rate","Sycophancy fraction"),("correction_rate","Correction fraction")])
    lines += [""] + _qualitative(rows,patterns)
    lines += ["## Signal and limitations", ""]
    if not analysis["bootstrap"]["contrasts"]:
        lines += ["Paired inference is unavailable: no complete low/neutral/high triplets remain. "
                  "There is no measurable confidence contrast yet; descriptive counts alone do not answer the hypothesis.",""]
    for row in analysis["bootstrap"]["contrasts"]:
        if row["outcome"] == "sycophancy" and row["contrast"] == "high - low":
            direction = "positive" if row["estimate"] > 0 else "negative" if row["estimate"] < 0 else "zero"
            lines.append(f"- {row['model']}: observed HIGH−LOW acceptance contrast is {direction} ({_pp(row['estimate'])}). "
                         f"CI status: {row['status']}. This is an automatic-label estimate, not a validated causal conclusion.")
    lines += ["", "A small hand-curated corpus and residual confidence-cue length/wording differences limit generalization. "
              "Unvalidated automatic labels can create or hide a signal. Missing/truncated responses and review flags are reported; "
              "the separate review-excluded analysis is a sensitivity check, not a replacement for human validation. "
              "No meaningful population claim follows solely from a nonsignificant p-value or a zero observed contrast.", ""]
    with _atomic_text_file(path) as stream:
        stream.write("\n".join(lines))


def analyze_run(run_dir: str | Path, output_dir: str | Path, *, n_bootstrap: int = 5000,
                seed: int = 20261006, annotation_path: str | Path | None = None) -> dict:
    """Analyze actual complete text responses; never create synthetic stand-ins."""
    run_dir, output_dir = Path(run_dir), Path(output_dir)
    frozen_cost_review = verify_frozen_cost_review(run_dir)
    manifest, records, collection = load_run(run_dir)
    valid = [row for row in records if row.get("status","success") in {"success","completed"}
             and isinstance(row.get("response"),str) and row["response"].strip()
             and row.get("finish_reason") not in {"length","max_tokens","content_filter"}]
    if not valid:
        raise ValueError("No complete, nonempty API responses available; no empirical report generated.")
    settings = manifest["specification"].get("config", {})
    budget_path = (resolve_recorded_path(settings["budget_path"], settings.get("run_dir"), run_dir)
                   if settings.get("budget_path") is not None else None)
    budget_audit = validate_budget_history(run_dir, budget_path,
                                          settings.get("budget_limit_usd", 8.0), relocate_paths=True)
    if budget_audit is not None:
        collection["budget"] = budget_audit
    rows = evaluate_records(valid)
    analysis = analyze_baseline(rows,n_bootstrap=n_bootstrap,seed=seed)
    sensitivity = analyze_baseline(rows,n_bootstrap=n_bootstrap,seed=seed,include_review=False)
    patterns = error_patterns(rows)
    collection["usage"] = {key: {"observed_subtotal":sum(row[key] for row in records if row.get(key) is not None)
                                                   if any(row.get(key) is not None for row in records) else None,
                                      "records_with_usage":sum(row.get(key) is not None for row in records),
                                      "records_missing_usage":sum(row.get(key) is None for row in records)}
                           for key in ("input_tokens","output_tokens","reasoning_tokens","cached_input_tokens","cache_write_tokens")}
    collection["usage"]["global_budget"] = collection.get("budget",{})
    annotation_path = Path(annotation_path) if annotation_path is not None else run_dir/"annotation.csv"
    if not annotation_path.exists():
        export_annotation(rows,annotation_path,size=min(200,len(rows)),seed=seed)
    human_rows = import_annotations(annotation_path,rows)
    human = agreement_metrics(human_rows)
    write_json(output_dir/"baseline_analysis.json",analysis)
    write_json(output_dir/"baseline_sensitivity_review_excluded.json",sensitivity)
    write_json(output_dir/"human_validation.json",human)
    write_json(output_dir/"baseline_collection.json",collection)
    write_table(run_dir/"evaluated_responses.csv",rows)
    for name in ("rates_by_confidence","rates_by_domain","rates_by_difficulty","cochran_q","mcnemar"):
        write_table(output_dir/"tables"/f"baseline_{name}.csv",analysis[name])
    write_table(output_dir/"tables"/"baseline_bootstrap_rates.csv",analysis["bootstrap"]["rates"])
    write_table(output_dir/"tables"/"baseline_bootstrap_contrasts.csv",analysis["bootstrap"]["contrasts"])
    write_table(output_dir/"tables"/"baseline_error_analysis.csv",patterns)
    write_baseline_report(manifest,collection,analysis,rows,patterns,human,output_dir/"baseline_results.md")
    usage_known = all(type(row.get("input_tokens")) is int and type(row.get("output_tokens")) is int for row in records)
    if frozen_cost_review:
        verify_frozen_cost_review(run_dir)
    elif (len(rows)==collection["planned_responses"] and collection.get("status")=="complete"
            and usage_known and budget_audit is not None and budget_audit["review_ready"]):
        write_json(run_dir/"cost_review.json",{
            "run_id":manifest["run_id"],"status":"reviewed","review_method":"automated_usage_and_completeness_check",
            "observed_usage_cost_usd":collection["budget"]["observed_usage_cost_usd"],
            "expected_evaluable_responses":len(rows),"global_budget_snapshot":collection["budget"],
            "note":"This is a cost/completeness gate, not human annotation or a provider invoice.",
        })
    elif (run_dir/"cost_review.json").exists():
        write_json(run_dir/"cost_review.json",{
            "run_id":manifest["run_id"],"status":"pending",
            "reason":"Collection completeness, known usage, and reconciled budget evidence are required.",
        })
    return {"run_id":manifest["run_id"],"n_evaluable":len(rows),"needs_human_review":analysis["metadata"]["needs_human_review"],
            "human_labels":human["n"],"report":str(output_dir/"baseline_results.md")}
