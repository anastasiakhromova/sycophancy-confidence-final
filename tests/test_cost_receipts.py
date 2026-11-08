"""Local-only authority lookup for frozen historical cost receipts."""
import hashlib
import json

import pytest

from sycophancy.cost_receipts import verify_frozen_cost_review


def test_unfrozen_run_has_normal_gate_behavior(tmp_path):
    run = tmp_path / "data/runs/main"
    run.mkdir(parents=True)
    assert verify_frozen_cost_review(run) is False


@pytest.mark.parametrize("sources", [None, [], {"data/runs/main/cost_review.json": "bad-hash"}])
def test_invalid_local_authority_refused(tmp_path, sources):
    run = tmp_path / "data/runs/main"
    run.mkdir(parents=True)
    manifest = tmp_path / "data/validation_v2/coordinator_manifest.json"
    manifest.parent.mkdir()
    manifest.write_text(json.dumps({"source_sha256": sources}))
    with pytest.raises(ValueError, match="Invalid frozen cost review"):
        verify_frozen_cost_review(run)


def test_missing_authority_with_present_evaluator_lock_refused(tmp_path):
    run = tmp_path / "data/runs/main"
    run.mkdir(parents=True)
    lock = tmp_path / "data/validation_v2/evaluator_lock.json"
    lock.parent.mkdir()
    lock.write_text("{}")
    with pytest.raises(ValueError, match="authority is missing"):
        verify_frozen_cost_review(run)


def test_nearest_study_does_not_inherit_outer_receipt_authority(tmp_path):
    root = tmp_path / "copy"
    run = root / "data/runs/main"
    run.mkdir(parents=True)
    for project, hashes in ((root, {}), (tmp_path, {"copy/data/runs/main/cost_review.json": hashlib.sha256(b"outer").hexdigest()})):
        manifest = project / "data/validation_v2/coordinator_manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"source_sha256": hashes}))
    assert verify_frozen_cost_review(run) is False
