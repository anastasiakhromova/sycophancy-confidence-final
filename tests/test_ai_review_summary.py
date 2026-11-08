import copy
import importlib.util
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "summarize_ai_review", Path(__file__).parents[1] / "scripts" / "summarize_ai_review.py")
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def judgment(**changes):
    return {"audit_id": "a", "ai_label": "CORRECT", "reviewer_id": "test-ai",
            "reason": "The false date is explicitly repaired.", "evidence": "1815", **changes}


def test_semantic_review_evidence_is_bound_to_original_text_without_mutation():
    sources = {"a": {"response": "The year was 1815, not 1817."}}
    rows = [judgment()]
    before = copy.deepcopy((sources, rows))
    assert review.validate_judgments(rows, sources, {"a"})["a"]["ai_label"] == "CORRECT"
    assert (sources, rows) == before


@pytest.mark.parametrize("rows", [[], [judgment(), judgment()], [judgment(audit_id="foreign")],
                                  [judgment(ai_label="human")], [judgment(evidence="made-up quote")]])
def test_missing_duplicate_foreign_invalid_or_unsupported_review_is_rejected(rows):
    with pytest.raises(ValueError):
        review.validate_judgments(rows, {"a": {"response": "1815"}}, {"a"})


def test_agreement_does_not_treat_unresolved_as_an_ordinary_class_or_human_label():
    stats = review.agreement([
        {"automatic_label": "CORRECT", "ai_label": "CORRECT"},
        {"automatic_label": "UNCERTAIN", "ai_label": "CORRECT"},
        {"automatic_label": "SYCOPHANTIC", "ai_label": "UNRESOLVED"},
    ])
    assert stats["n_reviewed"] == 3 and stats["n_determinate"] == 2 and stats["n_unresolved"] == 1
    assert stats["agreement_fraction_determinate"] == 0.5
    assert stats["confusion_matrix"] == [[1, 1, 0], [0, 0, 0], [0, 0, 0]]
    assert stats["matrix_rows"] == "AI assessment"
    assert "accuracy" not in stats


def test_all_unresolved_does_not_fabricate_agreement():
    stats = review.agreement([{"automatic_label": "UNCERTAIN", "ai_label": "UNRESOLVED"}])
    assert stats["agreement_fraction_determinate"] is None
    assert stats["macro_f1_vs_ai"] is None
