"""Offline challenge design, resume, accounting and provenance checks."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from sycophancy.challenge import (DOMAINS, build_challenge_plan, challenge_status,
                                 load_challenge_config, run_challenge)
from sycophancy.llm import LLMError, LLMResponse


@pytest.fixture
def challenge(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    (tmp_path / "configs").mkdir()
    source = tmp_path / "data/challenge_v1"
    source.mkdir(parents=True)
    rows = []
    for index in range(30):
        rows.append({"claim_id": f"CH{index + 1:03}", "domain": DOMAINS[index // 6],
            "false_claim": f"Synthetic false claim {index}.", "true_claim": f"Synthetic true claim {index}.",
            "knowledge_question": f"Synthetic neutral question {index}?", "true_answer": "true answer",
            "false_answer": "false answer", "true_aliases": ["true answer"], "false_aliases": ["false answer"],
            "source_url": "https://example.test/source", "source_title": "Synthetic fixture source",
            "source_evidence": "Synthetic fixture evidence", "rationale": "Synthetic fixture only"})
    (source / "claims.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    (source / "cues.json").write_text(json.dumps({"families": {
        family: {level: f"Synthetic {family} {level} cue." for level in ("low", "neutral", "high")}
        for family in ("A", "B", "C")}, "assessment_instruction": "Assess the statement.",
        "knowledge_instruction": "Answer in 1 to 3 sentences."}), encoding="utf-8")
    (source / "protocol.md").write_text("Synthetic offline protocol.\n", encoding="utf-8")
    old = tmp_path / "data/runs/budget.json"
    old.parent.mkdir(parents=True)
    old.write_text(json.dumps({"limit_usd": "8", "reservations": {
        "historical": {"actual_usd": "1.3652759", "reserved_usd": "2"}}}), encoding="utf-8")
    original_config = Path(__file__).resolve().parents[1] / "configs/challenge.toml"
    config_path = tmp_path / "configs/challenge.toml"
    config_path.write_bytes(original_config.read_bytes())
    return load_challenge_config(config_path)


class OfflineClient:
    def __init__(self, results=None):
        self.prompts = []
        self.preflight_count = 0
        self.results = list(results or [])
        self.last_raw_response = {"id": "synthetic-response", "usage": {"output_tokens": 20}}

    def preflight(self):
        self.preflight_count += 1

    def generate(self, prompt, seed=None):
        assert seed is None
        self.prompts.append(prompt)
        result = self.results.pop(0) if self.results else LLMResponse(
            text="Synthetic response", input_tokens=100, output_tokens=20,
            reasoning_tokens=5, provider_model="gpt-6-luna", provider_response_id="synthetic-response")
        if isinstance(result, Exception):
            raise result
        return result


def test_fixed_design_dry_run_is_pure_and_knowledge_first(challenge):
    before = {p: p.read_bytes() for p in challenge.project.rglob("*") if p.is_file()}
    specification, plan = build_challenge_plan(challenge)
    assert specification["design_counts"] == {"knowledge": 30, "false_assertion": 270, "true_control": 90}
    assert len(plan) == len({row["response_id"] for row in plan}) == 390
    assert all(row["task"] == "knowledge" for row in plan[:30])
    assert all(row["task"] != "knowledge" for row in plan[30:])
    assert all(row["prompt"].endswith("Answer in 1 to 3 sentences.") for row in plan[:30])
    assert all("Answer in 1 to 3 sentences." not in row["prompt"] for row in plan[30:])
    assert {row["confidence"] for row in plan if row["task"] == "knowledge"} == {"neutral"}
    assert build_challenge_plan(challenge) == (specification, plan)
    result = run_challenge(challenge, dry_run=True, client_factory=lambda _: pytest.fail("No dry-run client"))
    assert result["network_calls"] == 0
    assert result["maximum_cost_without_retries_usd"] < .5
    assert not challenge.run_dir.exists()
    assert all(path.read_bytes() == raw for path, raw in before.items())


def test_manifest_is_frozen_before_preflight_and_sources_cannot_change(challenge):
    class CheckingClient(OfflineClient):
        def preflight(self):
            assert (challenge.run_dir / "manifest.json").is_file()
            super().preflight()
    client = CheckingClient()
    assert run_challenge(challenge, preflight=True, client_factory=lambda _: client)["status"] == "preflight_ok"
    assert client.prompts == []
    challenge.cues_path.write_text(challenge.cues_path.read_text() + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frozen"):
        run_challenge(challenge, client_factory=lambda _: pytest.fail("No changed-source request"))


def test_resume_skips_saved_and_preserves_original_ledger(challenge):
    original = (challenge.project / "data/runs/budget.json").read_bytes()
    client = OfflineClient()
    first = run_challenge(challenge, max_new_requests=2, client_factory=lambda _: client)
    assert first["recorded_responses"] == 2
    second = run_challenge(challenge, max_new_requests=1, client_factory=lambda _: client)
    assert second["recorded_responses"] == 3
    assert len(client.prompts) == len(set(client.prompts)) == 3
    assert second["budget"]["n_attempts"] == 3
    assert second["budget"]["observed_usage_cost_usd"] == pytest.approx(.00006)
    assert (challenge.project / "data/runs/budget.json").read_bytes() == original
    rows = [json.loads(line) for line in (challenge.run_dir / "responses.jsonl").read_text().splitlines()]
    assert all(row["reasoning_tokens"] == 5 for row in rows)
    assert all(row["provider_raw_response"]["id"] == "synthetic-response" for row in rows)
    assert all(row["observed_usage_cost_usd"] == pytest.approx(.00002) for row in rows)


def test_incomplete_response_is_preserved_not_repeated_or_labeled(challenge):
    client = OfflineClient([LLMResponse(text="", input_tokens=100, output_tokens=512,
                                      reasoning_tokens=512, status="incomplete", incomplete_reason="max_output_tokens")])
    first = run_challenge(challenge, max_new_requests=1, client_factory=lambda _: client)
    assert first["incomplete_or_failed_responses"] == 1
    assert first["completed_responses"] == 0
    second = run_challenge(challenge, max_new_requests=1, client_factory=lambda _: client)
    assert len(client.prompts) == len(set(client.prompts)) == 2
    assert second["recorded_responses"] == 2
    assert second["semantic_labels_created"] is False


def test_errors_keep_unknown_billing_reserve_and_never_log_provider_text(challenge):
    client = OfflineClient([LLMError("secret-provider-message", retryable=True, safe_to_log=True)])
    result = run_challenge(challenge, max_new_requests=2, client_factory=lambda _: client, sleep=lambda _: None)
    assert result["recorded_responses"] == 1
    assert result["budget"]["n_attempts"] == 2
    assert result["budget"]["unresolved_reserved_usd"] > 0
    assert "secret-provider-message" not in (challenge.run_dir / "attempts.jsonl").read_text()


def test_missing_budget_history_and_changed_response_fail_closed(challenge):
    run_challenge(challenge, max_new_requests=1, client_factory=lambda _: OfflineClient())
    challenge.budget_path.unlink()
    with pytest.raises(ValueError, match="ledger missing"):
        run_challenge(challenge, client_factory=lambda _: pytest.fail("No reset spending"))
    response_file = challenge.run_dir / "responses.jsonl"
    row = json.loads(response_file.read_text())
    row["response"] = "Modified fixture response"
    response_file.write_text(json.dumps(row) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        challenge_status(challenge)


def test_cap_and_original_directory_cannot_be_repurposed(challenge):
    with pytest.raises(ValueError, match="cap"):
        build_challenge_plan(replace(challenge, budget_limit_usd=8))
    original = challenge.config_path.read_text()
    challenge.config_path.write_text(original.replace("budget_limit_usd = 0.50", "budget_limit_usd = 1.0"))
    with pytest.raises(ValueError, match="cap"):
        load_challenge_config(challenge.config_path)
    challenge.config_path.write_text(original.replace("../data/challenge_v1/run/budget.json", "../data/runs/budget.json"))
    with pytest.raises(ValueError, match="inside data/challenge_v1"):
        load_challenge_config(challenge.config_path)


def test_unavailable_model_stops_before_generation(challenge):
    class Unavailable(OfflineClient):
        def preflight(self):
            raise LLMError("Unavailable", status=404)
    client = Unavailable()
    with pytest.raises(LLMError):
        run_challenge(challenge, client_factory=lambda _: client)
    assert client.prompts == []
    assert not challenge.budget_path.exists()
