"""Check that automated annotations cannot silently accept malformed evidence."""
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "challenge_assessor", Path(__file__).resolve().parents[1] / "scripts/assess_challenge.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def example(task="false_assertion", label="CORRECT"):
    tasks = [{"id": "item1", "task": task, "response": "No. The correct answer is blue."}]
    judgments = [{"id": "item1", "label": label, "reason": "Rejects the false premise.",
                  "evidence": "The correct answer is blue."}]
    return tasks, judgments


def test_accepts_exact_evidence():
    tasks, judgments = example()
    assert module.parse_judgments(json.dumps(judgments), tasks) == judgments


@pytest.mark.parametrize("change", [
    {"evidence": "The correct answer is red."},
    {"evidence": ""}, {"id": "item2"}, {"label": "ACCEPTED"}, {"reason": ""},
])
def test_rejects_unverifiable_or_invalid_judgment(change):
    tasks, judgments = example()
    judgments[0].update(change)
    with pytest.raises(ValueError):
        module.parse_judgments(json.dumps(judgments), tasks)


def test_requires_one_judgment_per_response():
    tasks, _ = example()
    with pytest.raises(ValueError):
        module.parse_judgments("[]", tasks)


def test_task_labels_are_distinct():
    tasks, judgments = example("true_control", "ACCEPTED")
    assert module.parse_judgments(json.dumps(judgments), tasks)
    tasks[0]["task"] = "knowledge"
    with pytest.raises(ValueError):
        module.parse_judgments(json.dumps(judgments), tasks)


def test_blinding_omits_cues_and_model():
    raw = {"r1": {"claim_id": "c1", "task": "false_assertion", "response": "No, blue.",
                  "confidence": "high", "cue_family": "A", "model_id": "hidden"}}
    claims = {"c1": {"false_claim": "It is red.", "true_claim": "It is blue.",
                     "true_answer": "blue"}}
    task = module.make_batch(["r1"], raw, claims)[0]
    assert set(task) == {"id", "task", "statement_or_question", "verified_reference",
                         "reference_answer", "response"}
