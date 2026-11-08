"""Additive, offline evaluator validation. Never replace the frozen primary study.

Review packets contain only blinded evidence; coordinator files must not be
given to annotators. A retrospective candidate holdout is reserved by claim
before running v2. It is not a prospectively sequestered or representative test.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

STAGES = ("baseline", "main", "robustness")
LABELS = ("CORRECT", "SYCOPHANTIC", "UNCERTAIN", "MIXED", "UNRESOLVED")
CONDITIONS = ("low", "neutral", "high")
PROTOCOL = "offline-validation-v2-0"
TEXT_FIELDS = ("false_claim", "true_answer", "false_answer", "response")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True,
                               indent=2, allow_nan=False) + "\n", encoding="utf-8")


def identity(stage: str, row: Mapping) -> str:
    return "|".join((stage, str(row["run_id"]), str(row["response_id"])))


def opaque_id(stage: str, row: Mapping) -> str:
    return hashlib.sha256((PROTOCOL + "|" + identity(stage, row)).encode()).hexdigest()[:24]


def load_primary(project: Path) -> dict[str, list[dict]]:
    stages = {s: read_csv(project / "data/runs" / s / "evaluated_responses.csv") for s in STAGES}
    for stage, rows in stages.items():
        keys = [identity(stage, r) for r in rows]
        if not rows or len(keys) != len(set(keys)):
            raise ValueError("Empty or duplicate primary response identities: " + stage)
    return stages


def source_paths(project: Path) -> list[Path]:
    """Hash every existing primary/AI/human source, not just selected rows."""
    paths = set((project / "data/ai_review").glob("*"))
    for s in STAGES:
        paths.update(p for p in (project / "data/runs" / s).rglob("*") if p.is_file())
    paths.update((project / "data/raw").glob("claims_*.csv"))
    paths.update((project / "data/verification").glob("*"))
    paths.add(project / "src/sycophancy/evaluation.py")
    return sorted(p for p in paths if p.is_file())


def verify_primary_freeze(project: Path) -> None:
    design = json.loads((project / "data/verification/main_design.json").read_text(encoding="utf-8"))
    for relative, expected in design["files"].items():
        if digest(project / relative) != expected:
            raise ValueError("Frozen primary input has changed: " + relative)


def partition_claims(main: Sequence[Mapping], pilot: Sequence[Mapping],
                     reviewed: Sequence[Mapping]) -> tuple[list[str], list[str]]:
    """Exclude every previously reviewed or pilot claim, across all conditions."""
    known = {str(r["claim_id"]) for r in pilot} | {str(r["claim_id"]) for r in reviewed}
    population = {str(r["claim_id"]) for r in main}
    return sorted(population & known), sorted(population - known)


def prepare_study(project: Path, study_dir: Path, review_dir: Path, *, seed: int = 20261006) -> dict:
    """Create blank review packets once; refuse to overwrite any existing work."""
    from .human_review import make_packet, write_review_html
    project, study_dir, review_dir = project.resolve(), study_dir.resolve(), review_dir.resolve()
    if study_dir.exists() and any(study_dir.iterdir()):
        raise FileExistsError("Study exists; preserve review work. Use analyze or a new directory.")
    if review_dir.exists() and any(review_dir.iterdir()):
        raise FileExistsError("Review directory exists; preserve review work.")
    verify_primary_freeze(project)
    stages = load_primary(project)
    source = json.loads((project / "data/ai_review/source_manifest.json").read_text(encoding="utf-8"))
    reviewed = source["records"]
    lookup = {identity(s, r): r for s, rows in stages.items() for r in rows}
    selected = []
    seen = set()
    for r in reviewed:
        key = identity(r["stage"], r)
        if key in seen or key not in lookup:
            raise ValueError("Foreign or duplicate development audit record.")
        seen.add(key)
        original = lookup[key]
        if r.get("claim_id") != original["claim_id"]:
            raise ValueError("Development audit claim_id differs from its primary response.")
        if any(original[k] != r[k] for k in TEXT_FIELDS):
            raise ValueError("Development evidence differs from primary response.")
        selected.append((r["stage"], original))
    # Partition from canonical primary records, never unverified audit metadata.
    dev_claims, held_claims = partition_claims(stages["main"], stages["baseline"],
                                            [original for _, original in selected])
    reserved = set(held_claims)
    held = [("main", r) for r in stages["main"] if r["claim_id"] in reserved]
    if not held:
        raise ValueError("No unreviewed claim groups remain for a retrospective candidate holdout.")
    # Other repetitions of reserved claims are withheld from development too.
    held_other = [(s, r) for s, rows in stages.items() if s != "main"
                  for r in rows if r["claim_id"] in reserved]
    groups = {"development": selected, "candidate_holdout": held}
    public_packets, coordinator_records = {}, {}
    public_names = {"development": "review_a", "candidate_holdout": "review_b"}
    for part, records in groups.items():
        public = [{"review_id": opaque_id(s, r), **{k: r[k] for k in TEXT_FIELDS}}
                  for s, r in records]
        packet = make_packet(public, f"{PROTOCOL}-{public_names[part]}", "Model response review", seed)
        public_packets[part] = packet
        for stage, r in records:
            rid = opaque_id(stage, r)
            coordinator_records[rid] = {
                "stage": stage, "run_id": r["run_id"], "response_id": r["response_id"],
                "claim_id": r["claim_id"], "model": r["model"], "confidence": r["confidence"],
                "partition": part, "primary_label": r["label"],
            }
    source_hashes = {p.relative_to(project).as_posix(): digest(p) for p in source_paths(project)}
    manifest = {
        "schema_version": 1, "protocol": PROTOCOL, "seed": seed,
        "created_utc": datetime.now(timezone.utc).isoformat(), "human_annotation_status": "not_started",
        "source_sha256": source_hashes,
        "partitions": {
            "development": {"responses": len(selected), "claims": len({r["claim_id"] for _, r in selected}),
                            "stages": dict(Counter(s for s, _ in selected)),
                            "role": "Known AI-reviewed diagnostic examples; permitted for development, never a v2 test."},
            "candidate_holdout": {"responses": len(held), "claim_ids": held_claims,
                "claims": len(held_claims), "primary_label_counts": dict(Counter(r["label"] for _, r in held)),
                "reserved_other_stage_responses": len(held_other),
                "role": "Retrospective candidate holdout, excluded from current rule tuning by claim."},
        },
        "excluded_development_claim_ids": held_claims, "known_claim_ids": dev_claims,
        "packets": {k: {"packet_id": v["packet_id"], "packet_sha256": v["packet_sha256"],
                         "file": k + ".json", "html": public_names[k] + ".html"} for k, v in public_packets.items()},
        "records": coordinator_records,
        "limits": [
            "Partition is post hoc. The full corpus and earlier aggregate diagnostics were accessible before this split.",
            "Historical unseen-by-anyone status cannot be established; this is not a prospective blind test.",
            "All previously reviewed and pilot claim groups are excluded from the candidate holdout.",
            "Selection excludes the already reviewed non-CORRECT examples, so holdout class coverage is restricted.",
            "Development and candidate-holdout results are descriptive for their respective selected sets, not population accuracy.",
            "Human JSON attestation is self-declared provenance, not independent identity verification.",
            "No human annotations or adjudications have been generated by this preparation step.",
        ],
    }
    study_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)
    for part, packet in public_packets.items():
        save_json(study_dir / (part + ".json"), packet)
        write_review_html(packet, review_dir / (public_names[part] + ".html"))
    save_json(study_dir / "coordinator_manifest.json", manifest)
    return {"study_dir": str(study_dir), "review_dir": str(review_dir),
            "partitions": manifest["partitions"], "human_labels": 0}


def check_study(project: Path, study_dir: Path) -> dict:
    from .human_review import validate_packet
    manifest = json.loads((study_dir / "coordinator_manifest.json").read_text(encoding="utf-8"))
    if manifest.get("protocol") != PROTOCOL:
        raise ValueError("Unsupported validation protocol.")
    verify_primary_freeze(project)
    for relative, expected in manifest["source_sha256"].items():
        if digest(project / relative) != expected:
            raise ValueError("Protected evidence changed since validation intake: " + relative)
    for expected in manifest["packets"].values():
        packet = json.loads((study_dir / expected["file"]).read_text(encoding="utf-8"))
        validate_packet(packet)
        if packet.get("packet_sha256") != expected["packet_sha256"] or packet.get("packet_id") != expected["packet_id"]:
            raise ValueError("Review packet identity changed after partition freeze.")
    return manifest


def summarize_labels(rows: Sequence[Mapping], label_field: str) -> dict:
    counts = Counter(r[label_field] for r in rows)
    cells = []
    for model in sorted({r["model"] for r in rows}):
        for condition in CONDITIONS:
            cell = [r for r in rows if r["model"] == model and r["confidence"] == condition]
            if not cell:
                continue
            found = Counter(r[label_field] for r in cell)
            cells.append({"model": model, "confidence": condition, "n": len(cell),
                          "counts": {k: found[k] for k in LABELS},
                          "rates": {k: found[k] / len(cell) for k in LABELS}})
    return {"n": len(rows), "counts": {k: counts[k] for k in LABELS}, "by_model_condition": cells}


def paired_effects(rows: Sequence[Mapping], label_field: str, *, draws: int, seed: int) -> dict:
    """Claim-cluster bootstrap and exact tests for detector C and S endpoints.

    MIXED and UNRESOLVED remain in denominators; neither is recoded as semantic
    uncertainty. Tests treat each repetition separately and correct within the
    model/endpoint family. These are exploratory, label-dependent statistics.
    """
    import numpy as np
    from .analysis import exact_mcnemar, holm_correction
    if type(draws) is not int or draws < 100:
        raise ValueError("At least 100 bootstrap draws are required.")
    groups = defaultdict(dict)
    for row in rows:
        rep = int(row.get("repetition", 0) or 0)
        key = (row["model"], row["claim_id"], rep)
        c = row["confidence"]
        if c not in CONDITIONS or c in groups[key]:
            raise ValueError("Duplicate or invalid paired condition.")
        groups[key][c] = row[label_field]
    incomplete = [key for key, values in groups.items() if set(values) != set(CONDITIONS)]
    if incomplete:
        raise ValueError("Paired inference requires complete condition triplets.")
    contrasts, tests = [], []
    for model in sorted({k[0] for k in groups}):
        claims = sorted({k[1] for k in groups if k[0] == model})
        rng = np.random.default_rng(seed)
        samples = rng.integers(0, len(claims), size=(draws, len(claims)))
        for target in ("CORRECT", "SYCOPHANTIC"):
            numerator = np.zeros((len(claims), 3))
            denominator = np.zeros((len(claims), 3))
            for i, claim in enumerate(claims):
                blocks = [v for (m, cl, _), v in groups.items() if m == model and cl == claim]
                for block in blocks:
                    numerator[i] += [block[c] == target for c in CONDITIONS]
                    denominator[i] += 1
            original = numerator.sum(axis=0) / denominator.sum(axis=0)
            boot = numerator[samples].sum(axis=1) / denominator[samples].sum(axis=1)
            for lo, hi in ((0, 2), (1, 2), (0, 1)):
                interval = np.quantile(boot[:, hi] - boot[:, lo], [0.025, 0.975])
                contrasts.append({"model": model, "endpoint": target,
                    "contrast": f"{CONDITIONS[hi]} - {CONDITIONS[lo]}", "n_claims": len(claims),
                    "difference_pp": float(100 * (original[hi] - original[lo])),
                    "ci95_pp": (100 * interval).tolist(),
                    "degenerate_empirical_interval": bool(interval[0] == interval[1])})
            family = []
            for rep in sorted({k[2] for k in groups if k[0] == model}):
                blocks = [v for (m, _, r), v in sorted(groups.items()) if m == model and r == rep]
                for lo, hi in ((0, 1), (0, 2), (1, 2)):
                    result = exact_mcnemar([b[CONDITIONS[lo]] == target for b in blocks],
                                          [b[CONDITIONS[hi]] == target for b in blocks])
                    family.append({"model": model, "endpoint": target, "repetition": rep,
                                   "contrast": f"{CONDITIONS[hi]} - {CONDITIONS[lo]}", **result})
            for row, adjusted in zip(family, holm_correction([r["p_value"] for r in family])):
                row.update(p_holm=adjusted, holm_family_size=len(family))
            tests.extend(family)
    return {"claim_bootstrap_draws": draws, "seed": seed, "contrasts": contrasts, "mcnemar": tests,
            "interpretation": "Exploratory detector-label endpoints, not validated semantic effect estimates. Pointwise percentile intervals; Holm within model/endpoint across comparisons and repetitions. Zero-width empirical intervals do not prove equivalence."}


def _write_evaluated(path: Path, rows: list[dict]) -> None:
    columns = list(dict.fromkeys(k for r in rows for k in r))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v
                             for k, v in row.items()})


def _human_results(project: Path, study_dir: Path, manifest: dict, evaluated: dict,
                   submissions: Sequence[Path]) -> dict:
    from .human_review import (validate_submission, calculate_human_agreement, classification_metrics,
                               review_context, validate_translation)
    packets = {part: json.loads((study_dir / data["file"]).read_text(encoding="utf-8"))
               for part, data in manifest["packets"].items()}
    by_packet_id = {p["packet_id"]: (part, p) for part, p in packets.items()}
    auto = {opaque_id(s, r): r for s, rows in evaluated.items() for r in rows}
    people = defaultdict(list)
    result = {"status": "no_human_labels", "human_annotations": 0, "by_reviewer": [],
              "independent_agreement": [], "adjudication": "not_performed",
              "population_accuracy": None, "validated_sycophancy_recall": None,
              "provenance": "Any supplied human attestation is self-declared; software cannot verify annotator identity."}
    seen = set()
    for path in submissions:
        submission = json.loads(path.read_text(encoding="utf-8"))
        if submission.get("packet_id") not in by_packet_id:
            raise ValueError("Submission belongs to an unknown packet.")
        part, packet = by_packet_id[submission["packet_id"]]
        rows = validate_submission(submission, packet, allow_partial=True)
        context = review_context(submission)
        if context["translation_method"] != "none":
            translation_path = project / "data/review_ru" / (packet["packet_id"] + ".json")
            translation = json.loads(translation_path.read_text(encoding="utf-8"))
            validate_translation(packet, translation)
            if context["translation_sha256"] != translation["translation_sha256"]:
                raise ValueError("Submission uses a different translation version.")
        who = submission["annotator_id"].strip()
        key = (part, who)
        if key in seen:
            raise ValueError("Use one latest export per reviewer/packet, not duplicate versions.")
        seen.add(key)
        people[part].append(submission)
        # This later comparison intentionally does not reveal predictions in the UI.
        truth = [r["label"] for r in rows]
        entry = {"partition": part, "annotator_id": who, "n": len(rows),
                 "review_context": context,
                 "presentation_scope": ("AI-assisted Russian translation with English originals available; "
                                        "translation may affect judgments." if context["display_language"] == "ru"
                                        else "Original English texts."),
                 "packet_size": len(packet["items"]), "partial": len(rows) < len(packet["items"]),
                 "submission_sha256": digest(path), "sampling_scope": "Selected packet only; not population-weighted.",
                 "v1": classification_metrics(truth, [auto[r["review_id"]]["label"] for r in rows]),
                 "v2": classification_metrics(truth, [auto[r["review_id"]]["v2_label"] for r in rows])}
        result["by_reviewer"].append(entry)
        result["human_annotations"] += len(rows)
    for part, exports in people.items():
        for i, first in enumerate(exports):
            for second in exports[i + 1:]:
                result["independent_agreement"].append({"partition": part,
                    **calculate_human_agreement(first, second, packets[part])})
    if result["human_annotations"]:
        result["status"] = "self_declared_human_annotations_imported"
    return result


def analyze_study(project: Path, study_dir: Path, output_dir: Path, *, draws: int = 5000,
                  seed: int = 20261006, submissions: Sequence[Path] = ()) -> dict:
    """Freeze v2 code before computing any candidate-holdout outputs."""
    from . import evaluation_v2
    from .human_review import classification_metrics
    project, study_dir, output_dir = project.resolve(), study_dir.resolve(), output_dir.resolve()
    manifest = check_study(project, study_dir)
    if output_dir == project or output_dir.is_relative_to(project / "data/runs"):
        raise ValueError("Refusing to write over the primary study.")
    generated_targets = {
        (output_dir / filename).resolve()
        for filename in [*(stage + "_evaluated_v2.csv" for stage in STAGES),
                         "comparison.json", "comparison.md", "human_validation.json"]
    }
    protected_targets = {
        *(Path(path).resolve() for path in submissions),
        *((project / relative).resolve() for relative in manifest["source_sha256"]),
        *((study_dir / metadata["file"]).resolve() for metadata in manifest["packets"].values()),
        (study_dir / "coordinator_manifest.json").resolve(),
        (study_dir / "evaluator_lock.json").resolve(),
    }
    collisions = generated_targets & protected_targets
    if collisions:
        raise ValueError("Derived output collides with protected input: " + str(sorted(collisions)[0]))
    implementation = Path(evaluation_v2.__file__)
    current_lock = {"evaluator_sha256": digest(implementation),
                    "primary_evaluator_sha256": digest(project / "src/sycophancy/evaluation.py"),
                    "aliases_sha256": digest(project / "data/verification/main_answer_aliases.json"),
                    "coordinator_manifest_sha256": digest(study_dir / "coordinator_manifest.json"),
                    "packet_sha256": {part: metadata["packet_sha256"]
                                      for part, metadata in manifest["packets"].items()},
                    "source_file": "src/sycophancy/evaluation_v2.py"}
    lock_path = study_dir / "evaluator_lock.json"
    if lock_path.exists():
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        if any(lock.get(k) != v for k, v in current_lock.items()):
            raise ValueError("Evaluator, partition or review packet changed after holdout release. Create a new explicitly post-hoc study; do not retune this holdout.")
    else:
        lock = {**current_lock, "frozen_utc": datetime.now(timezone.utc).isoformat(),
                "note": "Written before first v2 corpus/candidate-holdout evaluation. Historical exposure limitations remain."}
        save_json(lock_path, lock)
    original = load_primary(project)
    aliases_payload = json.loads((project / "data/verification/main_answer_aliases.json").read_text(encoding="utf-8"))
    aliases = aliases_payload.get("aliases", aliases_payload)
    evaluated = {s: evaluation_v2.evaluate_records_v2(rows, aliases) for s, rows in original.items()}
    for stage, rows in evaluated.items():
        if len(rows) != len(original[stage]):
            raise ValueError("The new evaluator removed or added responses.")
        for before, after in zip(original[stage], rows):
            if any(after.get(k) != v for k, v in before.items()):
                raise ValueError("New evaluator changed a primary field.")
            if after.get("v2_label") not in LABELS:
                raise ValueError("Invalid new evaluator label.")
    stages = {}
    for stage, rows in evaluated.items():
        transitions = Counter((r["label"], r["v2_label"]) for r in rows)
        stages[stage] = {"v1": summarize_labels(rows, "label"), "v2": summarize_labels(rows, "v2_label"),
            "transitions": [{"v1": a, "v2": b, "n": n} for (a, b), n in sorted(transitions.items())],
            "v1_effects": paired_effects(rows, "label", draws=draws, seed=seed),
            "v2_effects": paired_effects(rows, "v2_label", draws=draws, seed=seed)}
    # AI judgments are development diagnostics only, never test truth or human labels.
    lookup = {identity(s, r): r for s, rows in evaluated.items() for r in rows}
    ai_rows = read_csv(project / "data/ai_review/ai_reviewed_responses.csv")
    ai_report = {}
    for stage in ("main", "robustness"):
        selected = [r for r in ai_rows if r["stage"] == stage]
        determinate = [r for r in selected if r["ai_label"] != "UNRESOLVED"]
        expected = [r["ai_label"] for r in determinate]
        ai_report[stage] = {
            "n_reviewed": len(selected), "n_determinate": len(determinate),
            "n_ai_unresolved": len(selected) - len(determinate),
            "v1": classification_metrics(expected, [lookup[identity(stage, r)]["label"] for r in determinate]),
            "v2": classification_metrics(expected, [lookup[identity(stage, r)]["v2_label"] for r in determinate]),
            "unresolved_v2_counts": dict(Counter(lookup[identity(stage, r)]["v2_label"]
                for r in selected if r["ai_label"] == "UNRESOLVED")),
        }
    held_claims = set(manifest["partitions"]["candidate_holdout"]["claim_ids"])
    held_rows = [r for r in evaluated["main"] if r["claim_id"] in held_claims]
    result = {
        "schema_version": 1, "protocol": PROTOCOL, "status": "exploratory_automatic_comparison",
        "lock": lock, "stages": stages,
        "candidate_holdout": {"n": len(held_rows), "n_claims": len(held_claims),
            "v1": summarize_labels(held_rows, "label"), "v2": summarize_labels(held_rows, "v2_label"),
            "accuracy": None, "scope": "Automatic summary of a retrospective selected claim set; automatic agreement is not accuracy. Any supplied human-reference comparisons are reported separately under human_validation."},
        "ai_development_diagnostics": {"scope": "Post-hoc agreement with previously seen AI judgments, not independent validation. AI UNRESOLVED excluded from determinate comparisons.", "stages": ai_report},
        "human_validation": _human_results(project, study_dir, manifest, evaluated, submissions),
        "protected_source_files": len(manifest["source_sha256"]), "original_primary_outputs_unchanged": True,
        "new_model_api_calls": 0,
        "limitations": manifest["limits"] + [
            "v2 is a deterministic heuristic, not a semantic oracle; unresolved cases remain visible.",
            "Extra categories change the codebook; v1/v2 results are separate exploratory analyses.",
            "Changes in agreement on development examples do not establish improved held-out accuracy.",
            "If the human reference contains no SYCOPHANTIC cases, sycophancy recall is not estimable.",
        ],
    }
    # Validate everything before writing derived artifacts, and recheck the evidence.
    check_study(project, study_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for stage, rows in evaluated.items():
        _write_evaluated(output_dir / (stage + "_evaluated_v2.csv"), rows)
    save_json(output_dir / "comparison.json", result)
    (output_dir / "comparison.md").write_text(render_report(result), encoding="utf-8")
    save_json(output_dir / "human_validation.json", result["human_validation"])
    return result


def render_report(result: dict) -> str:
    lines = ["# Evaluator v2: exploratory offline comparison", "",
        "This report preserves every primary response and v1 label. No new model calls were made.",
        "v2 rules were frozen before their first candidate-holdout evaluation; the partition itself is retrospective.", "",
        "## Observed automatic labels", "",
        "| Collection | Version | N | CORRECT | SYCOPHANTIC | UNCERTAIN | MIXED | UNRESOLVED |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for stage, data in result["stages"].items():
        for version in ("v1", "v2"):
            row = data[version]
            lines.append(f"| {stage} | {version} | {row['n']} | " + " | ".join(str(row["counts"][k]) for k in LABELS) + " |")
    lines += ["", "UNRESOLVED is evaluator abstention; UNCERTAIN is detected withholding of factual judgment.",
              "MIXED records incompatible endorsement and repair. These classes are not silently recoded as sycophancy or correction.",
              "", "## HIGH minus LOW detector-label contrasts", "",
              "| Collection | Model | Endpoint | v1 difference (pp) | v2 difference (pp) | v2 pointwise 95% CI (pp) |",
              "|---|---|---|---:|---:|---|"]
    for stage, data in result["stages"].items():
        before = {(r["model"], r["endpoint"], r["contrast"]): r for r in data["v1_effects"]["contrasts"]}
        for row in data["v2_effects"]["contrasts"]:
            if row["contrast"] != "high - low":
                continue
            prior = before[(row["model"], row["endpoint"], row["contrast"])]
            low, high = row["ci95_pp"]
            lines.append(f"| {stage} | {row['model']} | {row['endpoint']} | {prior['difference_pp']:.2f} | {row['difference_pp']:.2f} | [{low:.2f}, {high:.2f}] |")
    human = result["human_validation"]
    lines += ["", "Intervals resample whole claims, preserving conditions and repetitions. Degenerate empirical intervals do not establish equivalence.",
              "Exact paired tests and Holm families are included in comparison.json. These label-dependent analyses remain exploratory.",
              "", "## Independent human validation", "",
              f"Status: **{human['status']}**. Imported human judgments: **{human['human_annotations']}**.",
              "No blank or AI-provided fields are counted as human labels. There is no automatic consensus or fabricated adjudication.",
              "Human provenance is self-declared in submitted exports; software checks consistency, not annotator identity.",
              "Accuracy and sycophancy recall remain unvalidated without suitable independent labels.",
              "", "## Development AI agreement", "",
              "Detailed comparisons with existing AI judgments are in comparison.json, separately for main and robustness.",
              "They reuse examples seen during development and do not establish generalization or population accuracy.",
              "", "## Limits", ""]
    lines.extend("- " + text for text in result["limitations"])
    return "\n".join(lines) + "\n"
