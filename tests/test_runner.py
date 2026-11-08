from dataclasses import replace
import json
from pathlib import Path

import pytest

from sycophancy.experiment_config import ExperimentConfig, ModelConfig
from sycophancy.llm import BaseLLMClient, LLMError, LLMResponse
from sycophancy.runner import _run_lock, build_plan, read_jsonl, run_experiment


class FixtureClient(BaseLLMClient):
    """Synthetic output exists exclusively inside tests and their temporary directories."""
    def __init__(self, failure=None, interrupt_after=None):
        self.calls = []
        self.failure = failure
        self.interrupt_after = interrupt_after

    def generate(self, prompt, *, seed=None):
        if self.interrupt_after is not None and len(self.calls) == self.interrupt_after:
            raise KeyboardInterrupt
        self.calls.append((prompt, seed))
        if self.failure:
            error, self.failure = self.failure, None
            raise error
        return LLMResponse("test-only response", input_tokens=3, output_tokens=2, latency=0.2)


@pytest.fixture
def config(valid_rows, write_claim_csv, tmp_path):
    return ExperimentConfig(write_claim_csv(valid_rows), tmp_path / "run", (
        ModelConfig("fixture", "test-only-model", "llama_cpp", "http://127.0.0.1:8080/v1"),
    ), max_requests=100, retries=2, backoff_seconds=0)


def test_dry_run_no_clients_no_output_files(config):
    def forbidden(_):
        pytest.fail("dry-run instantiated a client")
    result = run_experiment(config, dry_run=True, client_factory=forbidden)
    assert result["planned_responses"] == 15 and result["status"] == "dry_run"
    assert not config.run_dir.exists()


def test_randomized_order_deterministic_and_seed_sensitive(config):
    first = build_plan(config)[1]
    assert first == build_plan(config)[1]
    assert [row["response_id"] for row in first] != [row["response_id"] for row in build_plan(replace(config, seed=17))[1]]
    assert sorted(row["request_order"] for row in first) == list(range(1, 16))


def test_success_is_persisted_before_next_request_and_resume_no_clients(config):
    class Inspecting(FixtureClient):
        def generate(self, prompt, *, seed=None):
            assert len(read_jsonl(config.run_dir / "responses.jsonl")) == len(self.calls)
            return super().generate(prompt, seed=seed)
    client = Inspecting()
    result = run_experiment(config, client_factory=lambda _: client)
    assert result["status"] == "complete" and len(client.calls) == 15
    assert result["physical_attempts"] == 15
    rows = read_jsonl(config.run_dir / "responses.jsonl")
    assert len(rows) == 15 and len({row["response_id"] for row in rows}) == 15
    required = {"run_id", "response_id", "claim_id", "domain", "confidence", "model", "model_id", "prompt",
                "response", "temperature", "request_order", "timestamp", "input_tokens", "output_tokens", "latency"}
    assert all(required <= row.keys() for row in rows)
    result2 = run_experiment(config, client_factory=lambda _: pytest.fail("completed resume created a client"))
    assert result2["physical_attempts"] == 15


def test_retry_records_all_attempts_and_backoff(config):
    client = FixtureClient(failure=LLMError("private error", retryable=True, status=429))
    sleeps = []
    result = run_experiment(replace(config, backoff_seconds=2), client_factory=lambda _: client, sleep=sleeps.append)
    assert result["physical_attempts"] == 16 and result["successful_responses"] == 15
    assert sleeps == [2]
    events = read_jsonl(config.run_dir / "attempts.jsonl")
    assert events[1]["status"] == "failed" and events[1]["http_status"] == 429
    assert "private error" not in (config.run_dir / "attempts.jsonl").read_text()


def test_max_requests_counts_retries_and_persists_across_resume(config):
    config = replace(config, max_requests=2)
    client = FixtureClient(failure=LLMError("retry", retryable=True))
    result = run_experiment(config, client_factory=lambda _: client)
    assert result["physical_attempts"] == 2 and result["successful_responses"] == 1
    result2 = run_experiment(config, client_factory=lambda _: pytest.fail("budget exhausted but client instantiated"))
    assert result2["physical_attempts"] == 2 and result2["budget_exhausted"]


def test_nonretryable_not_retried_on_resume(config):
    client = FixtureClient(failure=LLMError("auth failure", retryable=False))
    result = run_experiment(config, client_factory=lambda _: client)
    assert result["physical_attempts"] == 15 and result["successful_responses"] == 14
    run_experiment(config, client_factory=lambda _: pytest.fail("terminal failure retried"))


def test_interruption_resume_preserves_success_and_counts_uncertain_attempt(config):
    client = FixtureClient(interrupt_after=2)
    result = run_experiment(config, client_factory=lambda _: client)
    assert result["status"] == "interrupted" and result["successful_responses"] == 2
    assert result["physical_attempts"] == 3
    resumed = FixtureClient()
    final = run_experiment(config, client_factory=lambda _: resumed)
    assert len(resumed.calls) == 13 and final["physical_attempts"] == 16
    assert not {prompt for prompt, _ in client.calls} & {prompt for prompt, _ in resumed.calls}


@pytest.mark.parametrize("change", ["seed", "dataset", "template", "budget"])
def test_manifest_rejects_changed_inputs(config, change, monkeypatch):
    run_experiment(config, client_factory=lambda _: FixtureClient())
    if change == "seed":
        config = replace(config, seed=111)
    elif change == "budget":
        config = replace(config, max_requests=101)
    elif change == "dataset":
        config.dataset_path.write_bytes(config.dataset_path.read_bytes() + b"\n")
    else:
        monkeypatch.setattr("sycophancy.runner.PROMPT_TEMPLATE_VERSION", "changed")
    with pytest.raises(ValueError, match="manifest has changed"):
        run_experiment(config, client_factory=lambda _: pytest.fail("manifest mismatch reached client"))


@pytest.mark.parametrize("change", ["unknown", "duplicate", "stale", "no-attempt"])
def test_response_history_rejects_bad_rows(config, change):
    run_experiment(config, client_factory=lambda _: FixtureClient())
    path = config.run_dir / "responses.jsonl"
    rows = read_jsonl(path)
    if change == "unknown":
        rows[0]["response_id"] = "unknown"
    elif change == "duplicate":
        rows.append(rows[0])
    elif change == "stale":
        rows[0]["prompt"] = "changed"
    else:
        (config.run_dir / "attempts.jsonl").write_text("", encoding="utf-8")
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    with pytest.raises(ValueError):
        run_experiment(config, client_factory=lambda _: pytest.fail("bad history reached client"))


def test_jsonl_partial_final_recovery_only(tmp_path):
    path = tmp_path / "events.jsonl"
    path.write_bytes(b'{"ok":1}\n{"broken":')
    with pytest.raises(ValueError):
        read_jsonl(path)
    assert read_jsonl(path, recover_tail=True) == [{"ok": 1}]
    assert path.read_bytes() == b'{"ok":1}\n'
    assert len(list(tmp_path.glob("events.jsonl.partial-*"))) == 1
    path.write_bytes(b'{"ok":1}\n{"broken":\n')
    with pytest.raises(ValueError):
        read_jsonl(path, recover_tail=True)
    path.write_bytes(b'{"ok":1}')
    assert read_jsonl(path, recover_tail=True) == [{"ok": 1}]
    assert path.read_bytes().endswith(b"\n")


@pytest.mark.parametrize("payload", [b'{"x":1,"x":2}\n', b'{"x":NaN}\n', b'[]\n', b'\n',
                                     b'{"x":1,"x":2}', b'{"x":NaN}', b'garbage', b'{"x":bogus}'])
def test_corrupt_complete_history_fails(tmp_path, payload):
    path = tmp_path / "bad.jsonl"
    path.write_bytes(payload)
    with pytest.raises(ValueError):
        read_jsonl(path, recover_tail=True)


def test_concurrent_run_locked(config):
    with _run_lock(config.run_dir):
        with pytest.raises(RuntimeError, match="Another process"):
            run_experiment(config, client_factory=lambda _: pytest.fail("locked runner created client"))


def test_zero_budget_no_network(config):
    result = run_experiment(replace(config, max_requests=0), client_factory=lambda _: pytest.fail("zero budget"))
    assert result["physical_attempts"] == 0


def test_repetitions_and_claim_sampling(config):
    config = replace(config, sample_claims=2, repetitions=3, models=(replace(config.models[0], seed=config.seed),))
    spec, plan = build_plan(config)
    assert len(plan) == 18 and len(spec["selected_claim_ids"]) == 2
    assert set(row["repetition"] for row in plan) == {1, 2, 3}
    for rep in (1, 2, 3):
        assert {row["generation_seed"] for row in plan if row["repetition"] == rep} == {config.seed + rep - 1}
    assert len({row["response_id"] for row in plan}) == 18


def test_verified_only_guard_and_sample_oversize(config):
    with pytest.raises(ValueError, match="requires every claim"):
        run_experiment(replace(config, require_verified=True), dry_run=True)
    with pytest.raises(ValueError, match="exceeds"):
        run_experiment(replace(config, sample_claims=100), dry_run=True)


def test_missing_manifest_never_adopts_existing_responses(config):
    config.run_dir.mkdir()
    (config.run_dir / "responses.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="without its original manifest"):
        run_experiment(config, client_factory=lambda _: pytest.fail("adopted unknown history"))


def test_all_models_preflight_before_any_requests(config):
    config = replace(config, models=(*config.models, ModelConfig("second", "second-test-model", "llama_cpp", "http://127.0.0.1:8081/v1")))
    client = FixtureClient()
    def factory(model):
        if model.alias == "second":
            raise LLMError("Missing API key")
        return client
    with pytest.raises(LLMError, match="Missing API key"):
        run_experiment(config, client_factory=factory)
    assert client.calls == []
    assert not (config.run_dir / "attempts.jsonl").exists()


def test_generation_seed_is_omitted_unless_supported_and_configured(config):
    assert all(row["generation_seed"] is None for row in build_plan(config)[1])


def test_incomplete_response_saved_without_retry(config):
    class Incomplete(FixtureClient):
        def generate(self,prompt,*,seed=None):
            self.calls.append((prompt,seed))
            return LLMResponse("",input_tokens=20,output_tokens=512,reasoning_tokens=512,
                               status="incomplete",incomplete_reason="max_output_tokens")
    client=Incomplete()
    result=run_experiment(config,client_factory=lambda _:client)
    assert result["physical_attempts"]==15
    rows=read_jsonl(config.run_dir / "responses.jsonl")
    assert len(rows)==15 and all(row["status"]=="incomplete" for row in rows)
    run_experiment(config,client_factory=lambda _:pytest.fail("incomplete results were retried"))


def test_unavailable_model_stops_whole_run(config):
    client=FixtureClient(failure=LLMError("model_not_found",status=404,safe_to_log=True))
    result=run_experiment(config,client_factory=lambda _:client)
    assert result["status"]=="stopped" and result["physical_attempts"]==1
    assert result["fatal_error"]=="model_not_found"


def test_global_budget_refuses_before_physical_attempt(config):
    config=replace(config,budget_path=config.run_dir.parent / "global-budget.json",budget_limit_usd=0,
                   models=(replace(config.models[0],model_id="gpt-6-luna"),))
    client=FixtureClient()
    result=run_experiment(config,client_factory=lambda _:client)
    assert result["status"]=="budget_exhausted" and result["physical_attempts"]==0
    assert client.calls==[]


def test_success_persisted_before_budget_settlement_error(config):
    from sycophancy.budget import BudgetExceeded
    class Budget:
        def reserve(self,model,prompt):
            return "reservation"
        def settle(self,reservation,response):
            assert len(read_jsonl(config.run_dir / "responses.jsonl"))==1
            raise BudgetExceeded("unexpected usage")
        def summary(self):
            return {"test_only":True}
    result=run_experiment(config,client_factory=lambda _:FixtureClient(),budget=Budget())
    assert result["status"]=="stopped" and result["successful_responses"]==1
    assert result["physical_attempts"]==1


def test_dry_run_budget_estimate_never_creates_ledger(config):
    config=replace(config,budget_path=config.run_dir.parent / "global-budget.json",
                   models=(replace(config.models[0],model_id="gpt-6-luna"),))
    result=run_experiment(config,dry_run=True)
    assert result["maximum_cost_without_retries_usd"]>0
    assert not config.budget_path.exists() and not config.run_dir.exists()


def test_missing_global_budget_history_blocks_resume_before_client(config):
    config=replace(config,budget_path=config.run_dir.parent / "global-budget.json",
                   models=(replace(config.models[0],model_id="gpt-6-luna"),))
    run_experiment(config,client_factory=lambda _:FixtureClient())
    assert all(row["budget_reservation_id"] for row in read_jsonl(config.run_dir / "responses.jsonl"))
    config.budget_path.unlink()
    with pytest.raises(ValueError):
        run_experiment(config,client_factory=lambda _:pytest.fail("missing ledger reached client"))


@pytest.mark.parametrize("failure", ["missing", "incomplete", "empty", "truncated", "unreviewed", "stale", "unknown_cost", "negative_cost", "short_review"])
def test_prerequisite_gate_blocks_before_clients(config, failure):
    prerequisite = config.run_dir.parent / "baseline-prerequisite"
    config = replace(config, prerequisite_run_dir=prerequisite)
    prerequisite.mkdir()
    summary = {"run_id":"baseline-id", "status":"complete", "planned_responses":15, "completed_responses":15}
    review = {"run_id":"baseline-id", "status":"reviewed", "observed_usage_cost_usd":0.01,
              "expected_evaluable_responses":15}
    if failure == "incomplete":
        summary["status"] = "incomplete"
    elif failure == "empty":
        summary.update(planned_responses=0, completed_responses=0)
    elif failure == "truncated":
        summary["completed_responses"] = 14
    elif failure == "unreviewed":
        review["status"] = "pending"
    elif failure == "stale":
        review["run_id"] = "older-run"
    elif failure == "unknown_cost":
        review["observed_usage_cost_usd"] = None
    elif failure == "negative_cost":
        review["observed_usage_cost_usd"] = -1
    elif failure == "short_review":
        review["expected_evaluable_responses"] = 14
    (prerequisite / "run_summary.json").write_text(json.dumps(summary),encoding="utf-8")
    if failure != "missing":
        (prerequisite / "cost_review.json").write_text(json.dumps(review),encoding="utf-8")
    with pytest.raises(ValueError, match="Prerequisite"):
        run_experiment(config,client_factory=lambda _:pytest.fail("unmet prerequisite reached client"))
    assert not config.run_dir.exists()


def test_prerequisite_gate_allows_reviewed_complete_run(config):
    prerequisite = config.run_dir.parent / "baseline-prerequisite"
    config = replace(config, prerequisite_run_dir=prerequisite)
    prerequisite.mkdir()
    (prerequisite / "run_summary.json").write_text(json.dumps({
        "run_id":"baseline-id", "status":"complete", "planned_responses":15, "completed_responses":15}),encoding="utf-8")
    (prerequisite / "cost_review.json").write_text(json.dumps({
        "run_id":"baseline-id", "status":"reviewed", "observed_usage_cost_usd":0.01,
        "expected_evaluable_responses":15}),encoding="utf-8")
    assert run_experiment(config,client_factory=lambda _:FixtureClient())["status"] == "complete"


def test_prerequisite_is_not_required_for_dry_run(config):
    config = replace(config,prerequisite_run_dir=config.run_dir.parent / "not-yet-run")
    assert run_experiment(config,dry_run=True)["status"] == "dry_run"


@pytest.mark.parametrize("failure",["deleted_ledger","absent_receipt","unknown_billing","overrun","different_ledger","missing_attempt_history"])
def test_new_stage_cannot_reset_predecessor_budget_evidence(config,failure):
    config=replace(config,budget_path=config.run_dir.parent/"global-budget.json",
                   models=(replace(config.models[0],model_id="gpt-6-luna"),))
    summary=run_experiment(config,client_factory=lambda _:FixtureClient())
    (config.run_dir/"cost_review.json").write_text(json.dumps({
        "run_id":summary["run_id"],"status":"reviewed","observed_usage_cost_usd":0.01,
        "expected_evaluable_responses":summary["completed_responses"]}),encoding="utf-8")
    next_config=replace(config,run_dir=config.run_dir.parent/"next-stage",prerequisite_run_dir=config.run_dir)
    if failure=="deleted_ledger":
        config.budget_path.unlink()
    elif failure=="missing_attempt_history":
        (config.run_dir/"attempts.jsonl").unlink()
    elif failure=="different_ledger":
        next_config=replace(next_config,budget_path=config.run_dir.parent/"fresh-budget.json")
    else:
        ledger=json.loads(config.budget_path.read_text())
        key=next(iter(ledger["reservations"]))
        if failure=="absent_receipt":
            del ledger["reservations"][key]
        elif failure=="unknown_billing":
            ledger["reservations"][key]["actual_usd"]=None
        else:
            ledger["reservations"][key]["reserve_exceeded"]=True
        config.budget_path.write_text(json.dumps(ledger),encoding="utf-8")
    with pytest.raises(ValueError,match="[Bb]udget|reservation|unresolved"):
        run_experiment(next_config,client_factory=lambda _:pytest.fail("lost predecessor budget reached client"))
    assert not next_config.run_dir.exists()


def test_parallel_next_stage_can_recheck_settled_predecessor(config):
    from sycophancy.budget import BudgetLedger
    from sycophancy.runner import _validate_prerequisite
    config=replace(config,budget_path=config.run_dir.parent/"global-budget.json",
                   models=(replace(config.models[0],model_id="gpt-6-luna"),))
    summary=run_experiment(config,client_factory=lambda _:FixtureClient())
    (config.run_dir/"cost_review.json").write_text(json.dumps({
        "run_id":summary["run_id"],"status":"reviewed","observed_usage_cost_usd":0.01,
        "expected_evaluable_responses":summary["completed_responses"]}),encoding="utf-8")
    next_config=replace(config,run_dir=config.run_dir.parent/"next-stage",prerequisite_run_dir=config.run_dir)
    # A sibling's new request is in flight; the predecessor's receipts are all settled.
    BudgetLedger(config.budget_path,config.budget_limit_usd).reserve(config.models[0],"test-only sibling request")
    _validate_prerequisite(next_config)
