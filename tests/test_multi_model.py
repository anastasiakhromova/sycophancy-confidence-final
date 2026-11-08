from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
import threading
import time

import pytest

from sycophancy.budget import BudgetLedger, BudgetExceeded
from sycophancy.experiment_config import ExperimentConfig, ModelConfig
from sycophancy.llm import BaseLLMClient, LLMError, LLMResponse
from sycophancy.multi_model import SerializedBudget, model_configs, run_multi_model
from sycophancy.runner import run_experiment


@pytest.fixture
def config(tmp_path):
    dataset = Path(__file__).parents[1] / "data/raw/claims_baseline.csv"
    models = tuple(ModelConfig(alias=name, model_id=name, provider="openai-responses",
                              base_url="https://api.openai.com/v1", api_key_env="OPENAI_API_KEY",
                              temperature=None, reasoning_effort="low", max_tokens=512)
                   for name in ("gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"))
    return ExperimentConfig(dataset_path=dataset, run_dir=tmp_path/"main", models=models,
                            max_requests=450, sample_claims=2, require_verified=True,
                            budget_path=tmp_path/"budget.json", budget_limit_usd=8)


class FakeClient(BaseLLMClient):
    def __init__(self, *, fail_preflight=False):
        self.fail_preflight=fail_preflight
        self.calls=0

    def preflight(self):
        if self.fail_preflight:
            raise LLMError("Mock unavailable model", status=404, safe_to_log=True)

    def generate(self, prompt, *, seed=None):
        self.calls += 1
        return LLMResponse("Mock test-only response", input_tokens=20, output_tokens=10,
                           reasoning_tokens=0, cached_input_tokens=0, cache_write_tokens=0)


def test_dry_run_has_no_clients_or_files(config):
    result=run_multi_model(config, dry_run=True, client_factory=lambda _:pytest.fail("client in dry run"))
    assert result["planned_responses"]==18
    assert result["max_concurrent_models"]==3
    assert not config.run_dir.exists()
    assert not config.budget_path.exists()


def test_request_cap_preserved_and_paths_isolated(config):
    configs=model_configs(replace(config,max_requests=10))
    assert [c.max_requests for c in configs]==[4,3,3]
    assert sum(c.max_requests for c in configs)==10
    assert len({c.run_dir for c in configs})==3
    assert all(c.budget_path==config.budget_path for c in configs)


def test_unavailable_model_stops_before_generation(config):
    clients={m.alias:FakeClient(fail_preflight=m.alias=="gpt-6-astra") for m in config.models}
    with pytest.raises(LLMError,match="unavailable"):
        run_multi_model(config,client_factory=lambda m:clients[m.alias])
    assert sum(c.calls for c in clients.values())==0
    assert not config.budget_path.exists()


def test_baseline_gate_before_client_creation(config):
    gated=replace(config,prerequisite_run_dir=config.run_dir.parent/"absent_baseline")
    with pytest.raises(ValueError):
        run_multi_model(gated,client_factory=lambda _:pytest.fail("client before baseline gate"))


def test_parallel_collection_resume_and_shared_ledger(config):
    clients={m.alias:FakeClient() for m in config.models}
    factory=lambda m:clients[m.alias]
    first=run_multi_model(config,client_factory=factory)
    assert first["status"]=="complete"
    assert first["completed_responses"]==18
    assert sum(c.calls for c in clients.values())==18
    ledger=json.loads(config.budget_path.read_text())
    assert len(ledger["reservations"])==18
    assert all(r["actual_usd"] is not None for r in ledger["reservations"].values())
    second=run_multi_model(config,client_factory=factory)
    assert second["status"]=="complete"
    assert sum(c.calls for c in clients.values())==18
    assert second["budget"]["unresolved_reserved_usd"]==0


def test_serialized_budget_prevents_lost_updates_and_overrun(config):
    shared=SerializedBudget(BudgetLedger(config.budget_path,0.01))
    model=config.models[0]
    def reserve(_):
        try:
            return shared.reserve(model,"test prompt")
        except BudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        ids=list(pool.map(reserve,range(40)))
    successful=[rid for rid in ids if rid]
    ledger=json.loads(config.budget_path.read_text())
    assert len(ledger["reservations"])==len(successful)
    assert 0<len(successful)<40
    assert shared.summary()["remaining_usd"]>=0


def test_changed_collection_configuration_is_rejected(config):
    run_multi_model(config,client_factory=lambda _:FakeClient())
    with pytest.raises(ValueError,match="specification changed"):
        run_multi_model(replace(config,seed=config.seed+1),client_factory=lambda _:FakeClient())


def test_coordinated_stop_preserves_unsent_rows_and_budget(config):
    stop=threading.Event()
    class StopAfterOne(FakeClient):
        def generate(self,prompt,*,seed=None):
            response=super().generate(prompt,seed=seed)
            stop.set()
            return response
    client=StopAfterOne()
    single=model_configs(config)[0]
    first=run_experiment(single,client_factory=lambda _:client,stop_event=stop)
    assert first["physical_attempts"]==1
    assert first["status"]=="interrupted"
    assert first["budget"]["n_attempts"]==1
    assert first["budget"]["unresolved_reserved_usd"]==0
    normal=FakeClient()
    resumed=run_experiment(single,client_factory=lambda _:normal)
    assert resumed["status"]=="complete"
    assert normal.calls==5
    assert resumed["physical_attempts"]==6


def test_cancelled_before_send_is_not_terminal(config):
    from sycophancy.multi_model import _CoordinatedClient
    stop=threading.Event()
    stop.set()
    with pytest.raises(LLMError) as caught:
        _CoordinatedClient(FakeClient(),stop).generate("unused")
    assert caught.value.retryable


@pytest.mark.parametrize("workers",[0,-1,True,1.5])
def test_invalid_worker_count(config,workers):
    with pytest.raises(ValueError,match="max_workers"):
        run_multi_model(config,max_workers=workers,dry_run=True)
