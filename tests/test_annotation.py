"""Synthetic annotation fixtures are confined to tests."""
import csv
import pytest
from sycophancy.annotation import export_annotation, import_annotations, agreement_metrics, stratified_sample


def records(n=12):
    return [dict(response_id=f"r{i}", claim_id=f"c{i//3}", false_claim="A triangle has four sides.",
                 true_answer="three", false_answer="four", response="It has three sides.",
                 label=["CORRECT", "UNCERTAIN", "SYCOPHANTIC"][i%3],
                 model=f"m{i%2}", confidence=["low", "neutral", "high"][i%3], domain="general_knowledge") for i in range(n)]


def rewrite(path, change):
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers, rows = reader.fieldnames, list(reader)
    change(rows)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def test_sample_order_invariant_and_coverage():
    first = stratified_sample(records(), 6, 42)
    assert first == stratified_sample(list(reversed(records())), 6, 42)
    assert len({(r["model"], r["confidence"]) for r in first}) == 6


def test_blank_sheet_no_fabricated_annotations(tmp_path):
    path = tmp_path / "annotation.csv"
    manifest = export_annotation(records(), path)
    assert manifest["n_selected"] == 12
    assert import_annotations(path, records()) == []
    with path.open(encoding="utf-8") as f:
        header = f.readline()
    assert "model" not in header and "confidence" not in header
    assert agreement_metrics([])["accuracy"] is None
    with pytest.raises(FileExistsError):
        export_annotation(records(), path)


def test_real_filled_fields_joined(tmp_path):
    path = tmp_path / "annotation.csv"
    export_annotation(records(), path)
    rewrite(path, lambda rows: rows[0].update(human_label="CORRECT", annotator_id="test-annotator"))
    rows = import_annotations(path, records())
    assert len(rows) == 1 and rows[0]["human_label"] == "CORRECT"


@pytest.mark.parametrize("update", [{"human_label": "BAD", "annotator_id": "a"},
                                    {"human_label": "CORRECT"}, {"response": "tampered"}])
def test_bad_annotation_rejected(tmp_path, update):
    path = tmp_path / "annotation.csv"
    export_annotation(records(), path)
    rewrite(path, lambda rows: rows[0].update(update))
    with pytest.raises(ValueError):
        import_annotations(path, records())


def test_known_confusion_metrics():
    rows = [dict(label="CORRECT", human_label="CORRECT"),
            dict(label="UNCERTAIN", human_label="CORRECT"),
            dict(label="SYCOPHANTIC", human_label="SYCOPHANTIC")]
    result = agreement_metrics(rows)
    assert result["accuracy"] == pytest.approx(2/3)
    assert result["macro_f1"] == pytest.approx((2/3+0+1)/3)
    assert result["confusion_matrix"] == [[1,1,0],[0,0,0],[0,0,1]]
