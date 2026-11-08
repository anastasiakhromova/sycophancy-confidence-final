import csv
import json
from collections import Counter
from pathlib import Path

from sycophancy.data import load_claims
from sycophancy.main_reporting import load_metadata
from sycophancy.validation import validate_claims

ROOT=Path(__file__).parents[1]


def test_main_corpus_has_150_valid_verified_balanced_claims():
    claims,report=validate_claims(load_claims(ROOT/"data/raw/claims_main.csv"))
    assert report.passed and len(claims)==150
    assert report.verified_claims==150 and report.duplicate_count==0
    assert set(report.claims_per_domain.values())=={30}


def test_source_ledger_matches_every_claim_without_human_review_claim():
    claims=load_claims(ROOT/"data/raw/claims_main.csv")
    evidence=[json.loads(line) for line in (ROOT/"data/verification/main_sources.jsonl").read_text(encoding="utf-8").splitlines()]
    sources={row["claim_id"]:row for row in evidence}
    assert len(sources)==len(evidence)==150
    assert set(sources)=={row["claim_id"] for row in claims}
    for row in claims:
        source=sources[row["claim_id"]]
        assert source["source_url"]==row["source"]
        assert source["false_claim"]==row["false_claim"]
        assert source["true_answer"]==row["true_answer"]
        assert source["false_answer"]==row["false_answer"]
        assert source["source_opened"] is True
        assert source["independent_human_review"] is False
        assert source["verification_method"]=="agent_source_review"
        assert source["evidence_summary"] and source["locator"]
        assert source["source_coverage"]["true_answer"]=="supported"


def test_difficulty_is_complete_and_explicitly_rubric_based():
    metadata=load_metadata(ROOT/"data/raw/claims_main_metadata.csv")
    assert len(metadata)==150
    assert Counter(row["difficulty"] for row in metadata.values())=={"easy":88,"medium":62}
    assert all(row["difficulty_reason"] for row in metadata.values())


def test_controlled_wording_revisions_are_logged():
    sources={row["claim_id"]:row for row in map(json.loads,(ROOT/"data/verification/main_sources.jsonl").read_text(encoding="utf-8").splitlines())}
    assert "green plants" not in sources["sci_019"]["false_claim"]
    assert "pre_main_wording_revision" in sources["sci_019"]
    assert "best known" not in sources["his_018"]["false_claim"]
    assert "pre_main_wording_revision" in sources["his_018"]
