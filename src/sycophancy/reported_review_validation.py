"""Reproduce agreement with an AI-origin reference from a review-summary transcription.

This input is distinct from an original review-form export. Validate its lineage
and retain that distinction in every output; never manufacture form attestations.
"""
from __future__ import annotations

from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from .validation_study import (check_study, digest, identity, load_primary,
                               save_json, TEXT_FIELDS)

CLASSES = ("CORRECT", "SYCOPHANTIC", "UNCERTAIN", "MIXED")
LABELS = (*CLASSES, "UNRESOLVED")
STATEMENT = "data/second_review/statement.json"
LABEL_FILE = "data/second_review/reported_labels.jsonl"
SOURCE_MANIFEST = "data/ai_review/source_manifest.json"
RECORDING_BASIS = "author_supplied_summary_of_second_reviewer_complete_agreement"
RECORDING_METHOD = "label_transcribed_by_reference_to_matching_existing_assessment"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _relative(project: Path, relative: str) -> Path:
    if not isinstance(relative, str):
        raise ValueError("Input path must be a relative string.")
    path = (project / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(project):
        raise ValueError("Input path must stay within project: " + str(relative))
    return path


def _unique(rows: Sequence[Mapping], field: str, source: str) -> dict:
    result = {}
    for row in rows:
        key = row.get(field)
        if not isinstance(key, str) or not key or key in result:
            raise ValueError(f"Missing or duplicate {field} in {source}.")
        result[key] = row
    return result


def classification_summary(reference: Sequence[str], prediction: Sequence[str]) -> dict:
    """Score resolved references; abstentions remain in the accuracy denominator.

    Fixed-four macro F1 explicitly assigns zero to an undefined class F1. A
    separate present-reference-class macro F1 avoids implying four-class support.
    Neither convention establishes performance for classes absent in reference.
    """
    if len(reference) != len(prediction):
        raise ValueError("Reference and prediction lengths differ.")
    if any(label not in CLASSES for label in reference) or any(label not in LABELS for label in prediction):
        raise ValueError("Unknown label or unresolved reference supplied to classifier metrics.")
    matrix = [[0] * len(LABELS) for _ in CLASSES]
    for expected, actual in zip(reference, prediction):
        matrix[CLASSES.index(expected)][LABELS.index(actual)] += 1
    n = len(reference)
    correct = sum(a == b for a, b in zip(reference, prediction))
    abstained = prediction.count("UNRESOLVED")
    per_class = {}
    for i, label in enumerate(CLASSES):
        tp = matrix[i][i]
        support = sum(matrix[i])
        predicted = sum(row[i] for row in matrix)
        denominator = support + predicted
        per_class[label] = {
            "support": support, "predicted": predicted, "true_positive": tp,
            "precision": tp / predicted if predicted else None,
            "recall": tp / support if support else None,
            "f1_zero_division": 2 * tp / denominator if denominator else 0.0,
            "reference_class_observed": bool(support),
        }
    present = [value["f1_zero_division"] for value in per_class.values() if value["support"]]
    return {
        "n": n, "correct": correct, "accuracy": correct / n if n else None,
        "n_abstained": abstained, "n_covered": n - abstained,
        "coverage": (n - abstained) / n if n else None,
        "covered_accuracy": correct / (n - abstained) if n > abstained else None,
        "macro_f1_fixed_four_zero_division": sum(v["f1_zero_division"] for v in per_class.values()) / 4 if n else None,
        "macro_f1_present_reference_classes": sum(present) / len(present) if present else None,
        "n_present_reference_classes": len(present), "per_class": per_class,
        "confusion_matrix": matrix, "matrix_rows": "reference", "matrix_columns": "prediction",
        "reference_labels": list(CLASSES), "prediction_labels": list(LABELS),
        "sycophancy_recall": per_class["SYCOPHANTIC"]["recall"],
    }


def validated_rows(project: Path) -> tuple[dict, list[dict], dict]:
    """Validate every join, summary count, protected source and frozen evaluator."""
    from . import evaluation, evaluation_v2

    project = project.resolve()
    manifest = check_study(project, project / "data/validation_v2")
    inputs = {STATEMENT: digest(project / STATEMENT), LABEL_FILE: digest(project / LABEL_FILE)}
    statement = _json(project / STATEMENT)
    required = {
        "schema_version": 1, "record_type": "reported_independent_second_review",
        "status": "independent_second_review_reported_complete",
        "information_source": "project_author_account_of_second_review",
        "original_second_reviewer_form_export_available": False,
        "independence_evidence": "author_report_of_review_procedure",
        "agreement_calculated_from_two_original_exports": None,
        "independent_two_human_annotator_agreement": None,
        "label_file": LABEL_FILE,
    }
    for name, expected in required.items():
        if name not in statement or statement[name] != expected:
            raise ValueError("Inconsistent statement provenance: " + name)
    protocol = statement.get("protocol", {})
    if (protocol.get("independently_assessed_before_comparison_reported") is not True
            or protocol.get("prior_labels_visible_during_assessment_reported") is not False
            or protocol.get("comparison_after_assessment_reported") is not True):
        raise ValueError("Reported review protocol is inconsistent.")
    if statement.get("label_file_sha256") != inputs[LABEL_FILE]:
        raise ValueError("Reported label file hash differs from statement.")
    source_hashes = statement.get("comparison_source_file_sha256", {})
    if SOURCE_MANIFEST not in source_hashes:
        raise ValueError("Comparison source manifest hash is missing.")
    for relative, expected in source_hashes.items():
        if not relative.startswith("data/ai_review/"):
            raise ValueError("Unexpected comparison source path.")
        actual = digest(_relative(project, relative))
        if actual != expected:
            raise ValueError("Comparison source hash mismatch: " + relative)
        inputs[relative] = actual
    source = _json(project / SOURCE_MANIFEST)
    if source.get("review_type") != "post_hoc_ai_semantic_review" or source.get("is_human_validation") is not False:
        raise ValueError("Original AI source provenance has changed.")
    source_records = _unique(source["records"], "audit_id", SOURCE_MANIFEST)
    decisions = {}
    for relative in sorted(source_hashes):
        if relative == SOURCE_MANIFEST:
            continue
        if not relative.endswith(".jsonl"):
            raise ValueError("Unexpected comparison decision source.")
        for record in _jsonl(project / relative):
            audit_id = record.get("audit_id")
            if not audit_id or audit_id in decisions or record.get("ai_label") not in LABELS:
                raise ValueError("Invalid or duplicate comparison decision.")
            decisions[audit_id] = (record, relative)
    reported = _unique(_jsonl(project / LABEL_FILE), "audit_id", LABEL_FILE)
    if set(reported) != set(source_records) or set(reported) != set(decisions):
        raise ValueError("Missing or foreign reported audit IDs or comparison decisions.")

    lock_path = project / "data/validation_v2/evaluator_lock.json"
    lock = _json(lock_path)
    checks = {
        "evaluator_sha256": digest(project / "src/sycophancy/evaluation_v2.py"),
        "primary_evaluator_sha256": digest(project / "src/sycophancy/evaluation.py"),
        "aliases_sha256": digest(project / "data/verification/main_answer_aliases.json"),
        "coordinator_manifest_sha256": digest(project / "data/validation_v2/coordinator_manifest.json"),
        "source_file": "src/sycophancy/evaluation_v2.py",
        "packet_sha256": {k: v["packet_sha256"] for k, v in manifest["packets"].items()},
    }
    if any(lock.get(k) != value for k, value in checks.items()):
        raise ValueError("Frozen evaluator or validation partition changed.")
    if (digest(Path(evaluation_v2.__file__)) != checks["evaluator_sha256"]
            or digest(Path(evaluation.__file__)) != checks["primary_evaluator_sha256"]):
        raise ValueError("Imported evaluator implementation differs from frozen project code.")
    primary = load_primary(project)
    aliases_payload = _json(project / "data/verification/main_answer_aliases.json")
    aliases = aliases_payload.get("aliases", aliases_payload)
    evaluated = {s: evaluation_v2.evaluate_records_v2(rows, aliases) for s, rows in primary.items()}
    lookup = {identity(s, row): row for s, rows in evaluated.items() for row in rows}
    seen_response_ids, joined = set(), []
    for audit_id, record in sorted(reported.items()):
        original = source_records[audit_id]
        decision, source_file = decisions[audit_id]
        for field, expected in {
            "schema_version": 1, "review_id": statement["review_id"],
            "reviewer_id": statement["reviewer_id"], "recording_basis": RECORDING_BASIS,
            "recording_method": RECORDING_METHOD, "direct_item_level_export": False,
            "independently_assessed_before_comparison_reported": True,
            "review_statement": STATEMENT, "comparison_source_file": source_file,
            "comparison_source_file_sha256": source_hashes[source_file],
            "comparison_ai_label": decision["ai_label"],
            "reported_human_label": decision["ai_label"],
        }.items():
            if field not in record or record[field] != expected:
                raise ValueError("Reported label provenance or comparison differs: " + field)
        for field in ("stage", "run_id", "response_id", "claim_id", "response_sha256"):
            if record.get(field) != original.get(field):
                raise ValueError("Reported/source identity differs: " + field)
        key = identity(record["stage"], record)
        if record["stage"] not in ("main", "robustness") or key not in lookup or key in seen_response_ids:
            raise ValueError("Foreign or duplicate primary response identity.")
        seen_response_ids.add(key)
        response = lookup[key]
        if response["claim_id"] != record["claim_id"] or any(response[k] != original[k] for k in TEXT_FIELDS):
            raise ValueError("Source evidence differs from primary response.")
        response_hash = hashlib.sha256(response["response"].encode("utf-8")).hexdigest()
        if response_hash != record["response_sha256"]:
            raise ValueError("Response text hash mismatch.")
        if response["label"] not in CLASSES or response["v2_label"] not in LABELS:
            raise ValueError("Invalid frozen evaluator label.")
        joined.append({"audit_id": audit_id, "stage": record["stage"], "run_id": record["run_id"],
                       "response_id": record["response_id"], "claim_id": record["claim_id"],
                       "response_sha256": response_hash, "reference_label": record["reported_human_label"],
                       "v1_label": response["label"], "v2_label": response["v2_label"],
                       "included_in_metrics": record["reported_human_label"] != "UNRESOLVED"})
    stage_counts = dict(Counter(r["stage"] for r in joined))
    label_counts = dict(Counter(r["reference_label"] for r in joined))
    if (statement.get("reported_reviewed_count") != len(joined)
            or statement.get("reported_matching_count") != len(joined)
            or statement.get("reported_disagreement_count") != 0
            or statement.get("reported_agreement_fraction") != 1.0
            or statement.get("counts_by_stage") != stage_counts
            or source.get("scope") != stage_counts
            or statement.get("transcribed_label_counts") != label_counts):
        raise ValueError("Review summary counts disagree with validated items.")
    for relative in ("data/validation_v2/coordinator_manifest.json", "data/validation_v2/evaluator_lock.json",
                     "data/verification/main_design.json", "data/verification/main_answer_aliases.json",
                     "src/sycophancy/evaluation.py", "src/sycophancy/evaluation_v2.py"):
        inputs[relative] = digest(project / relative)
    inputs.update(manifest["source_sha256"])
    for relative in ("src/sycophancy/reported_review_validation.py", "scripts/analyze_reported_review.py"):
        if (project / relative).is_file():
            inputs[relative] = digest(project / relative)
    return statement, joined, inputs


def summarize(rows: Sequence[Mapping]) -> dict:
    resolved = [r for r in rows if r["included_in_metrics"]]
    excluded = [r for r in rows if not r["included_in_metrics"]]
    return {
        "n_reviewed": len(rows), "n_determinate": len(resolved),
        "n_reference_unresolved": len(excluded),
        "reference_counts": dict(sorted(Counter(r["reference_label"] for r in rows).items())),
        **{version: classification_summary([r["reference_label"] for r in resolved],
                                           [r[version + "_label"] for r in resolved]) for version in ("v1", "v2")},
        "excluded_reference_unresolved_predictions": {
            version: dict(sorted(Counter(r[version + "_label"] for r in excluded).items()))
            for version in ("v1", "v2")},
    }


def _markdown(result: dict) -> str:
    pooled = result["scopes"]["pooled"]
    present = ", ".join(k for k, value in pooled["v1"]["per_class"].items() if value["support"])
    lines = ["# Evaluator agreement with the selected AI-origin reference", "",
             f"The author reports that a second reviewer independently assessed {pooled['n_reviewed']} responses before viewing the existing decisions and agreed with all of them. Original second-reviewer exports are unavailable. The saved item-level rows were transcribed from the author's complete-agreement summary, not independently preserved annotations.", "",
             "The author approved the existing AI semantic judgments, rather than producing de novo independent labels. The transcribed reference reproduces those AI judgments. No inter-rater reliability was measured from two original annotation sets; the metrics below describe reference agreement, not validated human accuracy.", "",
             f"This is a selected development sample, not population accuracy or a held-out test. {pooled['n_reference_unresolved']} UNRESOLVED references are excluded. The {pooled['n_determinate']} resolved references support these classes: {present}. Recall cannot be estimated for classes without reference examples.", "",
             "| Scope | Evaluator | Matches / resolved | Reference agreement | Fixed-four macro F1* | Present-class macro F1 | Coverage | Covered agreement |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    for scope, group in result["scopes"].items():
        for version in ("v1", "v2"):
            m = group[version]
            def number(value):
                return "NA" if value is None else f"{value:.4f}"
            lines.append(f"| {scope} | {version} | {m['correct']}/{m['n']} | {number(m['accuracy'])} | {number(m['macro_f1_fixed_four_zero_division'])} | {number(m['macro_f1_present_reference_classes'])} | {number(m['coverage'])} | {number(m['covered_accuracy'])} |")
    lines += ["", "*Fixed-four macro F1 uses CORRECT, SYCOPHANTIC, UNCERTAIN, MIXED and zero_division=0. Unsupported classes contribute zero by convention; this does not validate those classes. Present-class macro F1 uses only classes occurring in the reference (here CORRECT).", "",
              "An evaluator's UNRESOLVED output is an abstention, not model uncertainty. It counts as a nonmatch in overall reference agreement and as a false negative for its reference class. Coverage and covered agreement are reported separately; 100% covered agreement is not 100% overall agreement. The JSON keys accuracy and covered_accuracy retain their original names for compatibility and denote these reference-agreement rates.", "",
              "Files: summary.json - metrics and provenance; joined_labels.csv - auditable joins; confusion_matrices.csv - counts including zero-support rows; 07_human_confusion_matrix.png/.pdf - pooled comparison. No model API calls or changes to frozen study data.", ""]
    return "\n".join(lines)


def analyze_reported_review(project: Path, output_dir: Path | None = None) -> dict:
    project = project.resolve()
    output_dir = (output_dir or project / "reports/reviewer_validation").resolve()
    if not output_dir.is_relative_to(project / "reports") or output_dir in (project / "reports", project / "reports/evaluator_v2"):
        raise ValueError("Derived output must use a separate directory within reports.")
    statement, rows, inputs = validated_rows(project)
    result = {
        "schema_version": 1, "status": "selected_ai_origin_reference_agreement",
        "review_id": statement["review_id"], "reference_recording_method": statement["item_level_recording_method"],
        "review_procedure": "Author-reported procedure: " + statement["statement_en"],
        "independence_evidence": statement["independence_evidence"],
        "reference_origin": "AI semantic judgments reproduced by transcription from the author's complete-agreement summary, not independently preserved reviewer annotations.",
        "author_review_role": "Approval of existing AI judgments, not de novo independent labels.",
        "validated_human_accuracy": None,
        "measured_inter_rater_reliability": None,
        "original_second_reviewer_form_export_available": False,
        "agreement_calculated_from_two_original_exports": None,
        "independent_two_human_annotator_agreement": None,
        "reported_comparison_matches": statement["reported_matching_count"],
        "reported_comparison_total": statement["reported_reviewed_count"],
        "population_accuracy": None, "validated_sycophancy_recall": None,
        "scopes": {stage: summarize([r for r in rows if r["stage"] == stage]) for stage in ("main", "robustness")},
        "metric_conventions": {
            "accuracy": "Agreement with the selected AI-origin reference: matches / resolved references; evaluator abstentions count as nonmatches. Not validated human accuracy.",
            "reference_unresolved": "Excluded from all classification denominators; counts and predictions shown separately.",
            "macro_f1_fixed_four_zero_division": "Arithmetic mean over CORRECT, SYCOPHANTIC, UNCERTAIN, MIXED; undefined class F1=0. Unsupported classes are unvalidated.",
            "macro_f1_present_reference_classes": "Arithmetic mean only over classes with positive reference support.",
            "coverage": "Non-UNRESOLVED predictions / resolved references.",
            "covered_accuracy": "Reference agreement on covered responses: matches / non-UNRESOLVED predictions among resolved references. Not validated human accuracy.",
        },
        "limitations": statement["limits"] + [
            "The author approved existing AI judgments; the reported second review has no original exports. The transcribed reference is not independent human ground truth.",
            "No inter-rater reliability was measured from two original annotation sets.",
            "v2 was developed with these semantic-review examples; this comparison cannot establish held-out improvement."],
        "input_sha256": dict(sorted(inputs.items())), "original_primary_outputs_unchanged": True,
        "new_model_api_calls": 0,
    }
    result["scopes"]["pooled"] = summarize(rows)
    # All sources are checked before creating any derived file.
    for relative, expected in inputs.items():
        if digest(project / relative) != expected:
            raise ValueError("Input changed while computing metrics: " + relative)
    output_dir.mkdir(parents=True, exist_ok=True)
    save_json(output_dir / "summary.json", result)
    (output_dir / "summary.md").write_text(_markdown(result), encoding="utf-8")
    with (output_dir / "joined_labels.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with (output_dir / "confusion_matrices.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["scope", "evaluator", "reference", "prediction", "count"])
        for scope, group in result["scopes"].items():
            for version in ("v1", "v2"):
                for i, ref in enumerate(CLASSES):
                    for j, pred in enumerate(LABELS):
                        writer.writerow([scope, version, ref, pred, group[version]["confusion_matrix"][i][j]])
    return result


def render_confusion_figure(result: dict, output_dir: Path) -> None:
    """Create actual pooled confusion matrices, retaining unsupported rows."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    pooled = result["scopes"]["pooled"]
    total = pooled["n_determinate"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    for ax, version in zip(axes, ("v1", "v2")):
        metrics = result["scopes"]["pooled"][version]
        matrix = np.array(metrics["confusion_matrix"])
        ax.imshow(matrix, cmap="Blues", vmin=0, vmax=max(1, total), aspect="auto")
        ax.set_xticks(range(5), ["Correct", "Sycophantic", "Uncertain", "Mixed", "Abstain"], rotation=25, ha="right")
        ax.set_yticks(range(4), ["Correct", "Sycophantic", "Uncertain", "Mixed"])
        ax.set_xlabel("Evaluator prediction")
        ax.set_ylabel("Selected AI-origin reference")
        ax.set_title(f"{version}: {metrics['correct']}/{metrics['n']} matches ({metrics['accuracy']:.1%})")
        for i in range(4):
            for j in range(5):
                ax.text(j, i, str(matrix[i, j]), ha="center", va="center",
                        color="white" if matrix[i, j] > total / 2 else "#12233a", fontsize=12)
    fig.suptitle(f"AI-origin reference agreement: {total} resolved responses", fontsize=15, y=.98)
    fig.text(.5, .025, f"{pooled['n_reference_unresolved']} unresolved references excluded. Zero-support classes are unvalidated.\n"
             "Author reports second-review agreement; rows transcribed from summary; original exports unavailable.\n"
             "No measured inter-rater reliability or validated human accuracy; development diagnostics only.",
             ha="center", va="bottom", fontsize=9)
    fig.tight_layout(rect=(0, .19, 1, .94))
    output_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf"):
        fig.savefig(output_dir / ("07_human_confusion_matrix." + suffix), dpi=190,
                    metadata={"CreationDate": None} if suffix == "pdf" else None)
    plt.close(fig)
