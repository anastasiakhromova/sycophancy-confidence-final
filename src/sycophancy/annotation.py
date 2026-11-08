"""Blinded review sheets and strict imports of actual human annotations."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import random
from typing import Mapping, Sequence

from .data import _atomic_text_file
from .evaluation import ResponseLabel

REVIEW_COLUMNS = (
    "response_id", "claim_id", "false_claim", "true_answer", "false_answer", "response",
    "human_label", "annotator_id", "annotation_notes",
)
_IMMUTABLE = REVIEW_COLUMNS[:6]


def stratified_sample(rows: Sequence[Mapping], size: int = 200, seed: int = 20261006) -> list[dict]:
    """Seeded round-robin over observed model/condition/domain/label strata.

    It prioritizes coverage over proportional sampling. The resulting evaluator
    agreement is descriptive for the sampled set, not population-weighted accuracy.
    """
    if type(size) is not int or size < 1:
        raise ValueError("Annotation sample size must be positive.")
    if len({row["response_id"] for row in rows}) != len(rows):
        raise ValueError("Duplicate response_id in annotation population.")
    groups = defaultdict(list)
    for row in sorted(rows, key=lambda row: row["response_id"]):
        groups[tuple(row.get(key, "unknown") for key in ("model", "confidence", "domain", "label"))].append(dict(row))
    rng = random.Random(seed)
    keys = sorted(groups)
    rng.shuffle(keys)
    for values in groups.values():
        rng.shuffle(values)
    selected = []
    while len(selected) < min(size, len(rows)):
        for key in keys:
            if groups[key] and len(selected) < size:
                selected.append(groups[key].pop())
    rng.shuffle(selected)
    return selected


def _record_hash(row: Mapping) -> str:
    payload = {key: str(row.get(key, "")) for key in _IMMUTABLE}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def export_annotation(rows: Sequence[Mapping], path: str | Path, *, size: int = 200, seed: int = 20261006) -> dict:
    """Write empty human fields; never overwrite a sheet containing human work."""
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"Annotation sheet already exists; preserve human work: {path}")
    selected = stratified_sample(rows, size, seed)
    manifest_path = path.with_suffix(".manifest.json")
    if manifest_path.exists():
        raise FileExistsError(f"Annotation manifest already exists: {manifest_path}")
    manifest = {
        "seed": seed, "sampling": "round-robin model/confidence/domain/automatic-label strata",
        "n_population": len(rows), "n_selected": len(selected),
        "human_annotation_status": "not_started",
        "blinding": "Model, confidence condition, and automatic labels omitted from annotation CSV.",
        "records": {str(row["response_id"]): {
            "sha256": _record_hash(row),
            **{key: row.get(key) for key in ("model", "confidence", "domain", "label", "needs_human_review")},
        } for row in selected},
    }
    with _atomic_text_file(path) as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in selected:
            writer.writerow({column: row.get(column, "") if column in _IMMUTABLE else "" for column in REVIEW_COLUMNS})
    with _atomic_text_file(manifest_path) as stream:
        json.dump(manifest, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")
    return manifest


def import_annotations(path: str | Path, records: Sequence[Mapping]) -> list[dict]:
    """Join nonblank human labels to immutable raw records; require annotator ID.

    Blank rows remain pending. A valid CSV format is not proof that a human
    performed the work; the researcher must establish annotator provenance.
    """
    path = Path(path)
    manifest = json.loads(path.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    originals = {str(row["response_id"]): row for row in records}
    if len(originals) != len(records):
        raise ValueError("Duplicate response_id in reference records.")
    results, seen = [], set()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != list(REVIEW_COLUMNS):
            raise ValueError("Annotation CSV columns were changed.")
        for row in reader:
            response_id = row["response_id"]
            if response_id in seen or response_id not in manifest["records"] or response_id not in originals:
                raise ValueError(f"Duplicate or unknown annotation response_id: {response_id}")
            seen.add(response_id)
            expected = manifest["records"][response_id]["sha256"]
            if _record_hash(row) != expected or _record_hash(originals[response_id]) != expected:
                raise ValueError(f"Annotation source text or reference record changed: {response_id}")
            label = row["human_label"].strip()
            if not label:
                continue
            if label not in {label.value for label in ResponseLabel}:
                raise ValueError(f"Invalid human_label for {response_id}: {label!r}")
            if not row["annotator_id"].strip():
                raise ValueError(f"Missing annotator_id for labeled response {response_id}")
            results.append({**originals[response_id], "human_label": label,
                            "annotator_id": row["annotator_id"].strip(), "annotation_notes": row["annotation_notes"]})
    if seen != set(manifest["records"]):
        raise ValueError("Annotation rows were removed; leave pending human_label cells blank instead.")
    return results


def agreement_metrics(rows: Sequence[Mapping]) -> dict:
    """Unweighted sampled-set accuracy, fixed-three-class macro F1 and confusion."""
    labels = [label.value for label in ResponseLabel]
    if not rows:
        return {"status": "no_human_labels", "n": 0, "accuracy": None, "macro_f1": None,
                "labels": labels, "confusion_matrix": None}
    counts = Counter()
    for row in rows:
        if row.get("label") not in labels or row.get("human_label") not in labels:
            raise ValueError("Agreement metrics require valid automatic and human labels.")
        counts[row["human_label"], row["label"]] += 1
    matrix = [[counts[truth, predicted] for predicted in labels] for truth in labels]
    f1 = []
    for index in range(len(labels)):
        tp = matrix[index][index]
        fp = sum(row[index] for row in matrix) - tp
        fn = sum(matrix[index]) - tp
        f1.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0)
    return {"status": "available", "n": len(rows),
            "accuracy": sum(matrix[i][i] for i in range(len(labels))) / len(rows),
            "macro_f1": sum(f1) / len(labels), "labels": labels,
            "confusion_matrix": matrix, "matrix_rows": "human", "matrix_columns": "automatic",
            "scope": "unweighted stratified annotation sample; not population accuracy"}
