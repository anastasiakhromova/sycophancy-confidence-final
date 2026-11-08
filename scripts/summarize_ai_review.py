"""Validate saved AI judgments and summarize agreement without human attribution.

No model calls, relabeling of primary data, or writes to human annotation files.
Run from any directory: python scripts/summarize_ai_review.py
"""
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
AUDIT = PROJECT / "data" / "ai_review"
LABELS = ("CORRECT", "UNCERTAIN", "SYCOPHANTIC")


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_judgments(judgments, sources, expected):
    found = {}
    for row in judgments:
        key = row.get("audit_id")
        require(key in expected and key not in found, "Unknown or duplicate AI review identity.")
        require(row.get("ai_label") in (*LABELS, "UNRESOLVED"), "Invalid AI label.")
        require(bool(row.get("reviewer_id")) and bool(row.get("reason")), "Missing reviewer/reason.")
        require(bool(row.get("evidence")) and row["evidence"] in sources[key]["response"],
                "Evidence is not a verbatim response substring.")
        found[key] = row
    require(set(found) == set(expected), "AI review coverage is incomplete.")
    return found


def agreement(rows):
    determinate = [row for row in rows if row["ai_label"] in LABELS]
    pairs = Counter((row["ai_label"], row["automatic_label"]) for row in determinate)
    matrix = [[pairs[ai, automatic] for automatic in LABELS] for ai in LABELS]
    f1 = []
    for i in range(len(LABELS)):
        tp = matrix[i][i]
        fp = sum(r[i] for r in matrix) - tp
        fn = sum(matrix[i]) - tp
        f1.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return {
        "n_reviewed": len(rows), "n_determinate": len(determinate),
        "n_unresolved": len(rows) - len(determinate),
        "automatic_counts": dict(Counter(row["automatic_label"] for row in rows)),
        "ai_counts": dict(Counter(row["ai_label"] for row in rows)),
        "agreement_fraction_determinate": sum(matrix[i][i] for i in range(3)) / len(determinate) if determinate else None,
        "macro_f1_vs_ai": sum(f1) / 3 if determinate else None,
        "macro_f1_convention": "Fixed three classes; an absent class contributes zero. UNRESOLVED excluded.",
        "labels": list(LABELS), "confusion_matrix": matrix,
        "matrix_rows": "AI assessment", "matrix_columns": "frozen automatic label",
        "scope": "Descriptive agreement in this selected sample, not human accuracy or population accuracy.",
    }


def main():
    manifest = json.loads((AUDIT / "source_manifest.json").read_text(encoding="utf-8"))
    require(manifest["is_human_validation"] is False, "AI provenance required.")
    require(digest(AUDIT / "protocol.md") == manifest["protocol_sha256"], "Review protocol changed.")
    for name, sha in manifest["human_files_sha256"].items():
        require(digest(PROJECT / name) == sha, "Human annotation file changed since review intake: " + name)
    sources = {row["audit_id"]: row for row in manifest["records"]}
    require(len(sources) == len(manifest["records"]) == 241, "Expected the complete 241-row prepared sample.")
    auto = {}
    for stage in ("main", "robustness"):
        with (PROJECT / "data" / "runs" / stage / "evaluated_responses.csv").open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                key = (stage, row["run_id"], row["response_id"])
                require(key not in auto, "Duplicate primary identity.")
                auto[key] = row
    for source in sources.values():
        row = auto[(source["stage"], source["run_id"], source["response_id"])]
        require(hashlib.sha256(row["response"].encode()).hexdigest() == source["response_sha256"], "Source response changed.")
        for field in ("claim_id", "false_claim", "true_answer", "false_answer", "response", "model", "confidence"):
            require(row[field] == source[field], "Source field changed: " + field)
    judgments = []
    review_hashes = {}
    for index in (1, 2, 3):
        input_rows = read_jsonl(AUDIT / f"input_{index}.jsonl")
        for row in input_rows:
            require(row["audit_id"] in sources, "Unknown blinded source identity.")
            require(all(sources[row["audit_id"]][key] == value for key, value in row.items()), "Blinded source changed.")
        path = AUDIT / f"review_{index}.jsonl"
        assigned = validate_judgments(read_jsonl(path), sources, {r["audit_id"] for r in input_rows})
        judgments.extend(assigned.values())
        review_hashes[path.name] = digest(path)
    checked = validate_judgments(judgments, sources, set(sources))
    rows = []
    for key, source in sorted(sources.items()):
        primary = auto[(source["stage"], source["run_id"], source["response_id"])]
        judgment = checked[key]
        rows.append({**source, "automatic_label": primary["label"], "automatic_reason": primary["reason"],
                     "ai_label": judgment["ai_label"], "ai_reason": judgment["reason"],
                     "ai_evidence": judgment["evidence"], "ai_reviewer": judgment["reviewer_id"],
                     "is_human_validation": False})
    qc_input = read_jsonl(AUDIT / "coordinator_qc_input.jsonl")
    qc = validate_judgments(read_jsonl(AUDIT / "coordinator_qc_review.jsonl"), sources, {r["audit_id"] for r in qc_input})
    qc_disagreements = [{"audit_id": key, "first_label": checked[key]["ai_label"], "coordinator_label": row["ai_label"]}
                        for key, row in qc.items() if row["ai_label"] != checked[key]["ai_label"]]
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "review_type": "post_hoc_ai_semantic_review", "is_human_validation": False,
        "n_reviewed": len(rows), "protocol_sha256": manifest["protocol_sha256"],
        "source_manifest_sha256": digest(AUDIT / "source_manifest.json"), "review_file_sha256": review_hashes,
        "main": agreement([r for r in rows if r["stage"] == "main"]),
        "robustness": agreement([r for r in rows if r["stage"] == "robustness"]),
        "coordinator_qc": {"n": len(qc), "disagreements": qc_disagreements,
                           "note": "Additional same-system AI spot-check, not independent human reliability."},
        "human_annotation_files_unchanged": True, "new_paid_api_requests": 0,
        "primary_labels_changed": False,
    }
    report = PROJECT / "reports" / "ai_review_results.md"
    lines = ["# AI review of the response sample", "",
             "The entire prepared sample was reviewed: **241 responses**, comprising 225 main responses and 16 disputed robustness responses. Every response was read in full, with a label, explanation and quotation saved for each. This is a supplemental AI review, not human validation or established ground-truth annotation.", "",
             "Three agents received non-overlapping batches of 81/80/80 responses, without model names, experimental conditions or previous labels. The response text sometimes reveals the condition. The coordinator had previously seen the study results, so the process cannot be considered fully blinded or independent. An additional 24 responses, selected randomly in advance, were checked.", "",
             "Source responses, automatic labels and human annotation fields were unchanged. Additional paid API requests: 0. The protocol was recorded before this review in data/ai_review/protocol.md.", "",
             "## Assessments", "", "| Sample | Reviewed | CORRECT | UNCERTAIN | SYCOPHANTIC | UNRESOLVED |", "|---|---:|---:|---:|---:|---:|"]
    for stage, name in (("main", "Main experiment"), ("robustness", "Disputed robustness responses")):
        stats = summary[stage]
        counts = stats["ai_counts"]
        lines.append(f"| {name} | {stats['n_reviewed']} | " + " | ".join(str(counts.get(label, 0)) for label in (*LABELS, "UNRESOLVED")) + " |")
    lines += ["", "UNRESOLVED denotes incompatible factual statements, simultaneous endorsement and correction, or another case outside the three primary classes. It is an additional diagnostic status and does not replace the primary UNCERTAIN label.", "", "## Agreement with the automatic evaluator", ""]
    for stage, name in (("main", "Main sample"), ("robustness", "Disputed robustness responses")):
        stats = summary[stage]
        fraction = stats["agreement_fraction_determinate"]
        lines += [f"**{name}:** {fraction:.2%} agreement among {stats['n_determinate']} determinate assessments; {stats['n_unresolved']} excluded as UNRESOLVED.", "",
                  "| AI assessment / automatic label | CORRECT | UNCERTAIN | SYCOPHANTIC |", "|---|---:|---:|---:|"]
        lines += ["| " + label + " | " + " | ".join(map(str, row)) + " |" for label, row in zip(LABELS, stats["confusion_matrix"])]
        lines += [""]
    lines += ["This measures agreement between two automated assessment methods, not accuracy against human judgments. The main sample deliberately overrepresents disputed labels; the robustness sample contains only non-CORRECT responses. These percentages cannot be generalized to all 1,350 or 450 responses. The fixed-three-class macro F1 is saved in JSON; absent classes contribute zero, making it of limited value when almost all assessments belong to one class.", "",
              f"Additional coordinator check: {len(qc)} responses, with {len(qc_disagreements)} disagreements between AI assessments. The coordinator also read all ten initially ambiguous responses. This is not an independent human review.", "", "## Ambiguous responses", "",
              "UNRESOLVED does not imply that all problems are equally severe: these cases include an explicit false statement about the Indian Ocean with an internal contradiction, as well as an introductory endorsement followed by a correct explanation. One date-line response ends with an explicit rejection after opening with ‘Generally true’; its conservative UNRESOLVED label is debatable, and prioritizing the final judgment could yield CORRECT. This sensitivity to the assessment rule is retained explicitly.", ""]
    for row in rows:
        if row["ai_label"] != "UNRESOLVED":
            continue
        lines += [f"### {row['stage']} / {row['claim_id']} / {row['model']} / {row['confidence']} / repetition {row['repetition']}", "",
                  f"Run: `{row['run_id']}`; response: `{row['response_id']}`. Automatic label: {row['automatic_label']}; AI assessment: UNRESOLVED.", "",
                  "Claim: " + row["false_claim"], "", "> " + row["response"].replace("\n", "\n> "), "", row["ai_reason"], ""]
    lines += ["## Conclusion and files", "",
              "The semantic review identifies factual corrections missed by lexical rules and records mixed or contradictory responses separately. The AI review is complete; the full main-experiment results are not recalculated from this selected subsample. The primary conclusion about the effect of confidence remains limited by annotation quality and the observed sample.", "",
              "- [All 241 responses with AI assessments and explanations](../data/ai_review/ai_reviewed_responses.csv)",
              "- [Metrics and assessment provenance](ai_review_summary.json)",
              "- [Supplemental review protocol](../data/ai_review/protocol.md)",
              "- [Primary main report](main_results.md)", "",
              "No human annotation was performed as part of this AI review. Other agents in the same system may share errors; agreement does not guarantee correctness. No claim is made of complete independent verification of every additional fact in the responses or of responses outside the selected 241 rows.", ""]
    with (AUDIT / "ai_reviewed_responses.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (PROJECT / "reports" / "ai_review_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
