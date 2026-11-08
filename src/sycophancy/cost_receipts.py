"""Preserve frozen historical cost gates during offline report reproduction."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


def verify_frozen_cost_review(run_dir: str | Path) -> bool:
    """Return whether the local study freezes this receipt, checking its bytes.

    A gate records the ledger state when its stage was cleared for further API
    collection. Subsequent stages may extend the shared ledger; current reports
    should reflect that extension without rewriting the historical gate. Locate
    the authority only from the actual run path so relocated archives never use
    a healthy original checkout to repair missing or changed historical input.
    """
    run_dir = Path(run_dir).resolve()
    receipt = run_dir / "cost_review.json"
    for root in (run_dir, *run_dir.parents):
        study = root / "data/validation_v2"
        manifest_path = study / "coordinator_manifest.json"
        if not manifest_path.exists():
            if (study / "evaluator_lock.json").exists():
                raise ValueError("Frozen cost review authority is missing: " + str(manifest_path))
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        sources = manifest.get("source_sha256")
        if not isinstance(sources, dict):
            raise ValueError("Invalid frozen cost review authority: source_sha256 mapping required.")
        relative = receipt.relative_to(root).as_posix()
        # The nearest local study is authoritative; do not search an outer copy.
        if relative not in sources:
            return False
        expected = sources[relative]
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Invalid frozen cost review hash: " + relative)
        if not receipt.is_file():
            raise ValueError("Frozen historical cost review is missing: " + relative)
        actual = hashlib.sha256(receipt.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("Frozen historical cost review hash mismatch: " + relative)
        return True
    return False
