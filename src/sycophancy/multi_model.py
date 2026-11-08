"""Run one durable collection per model, sharing a serialized budget ledger."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
import hashlib
import threading
from pathlib import Path

from .budget import create_budget
from .llm import BaseLLMClient, LLMError, create_client
from . import evaluation
from .runner import _save_json, _validate_prerequisite, build_plan, run_experiment


class SerializedBudget:
    """Serialize ledger read-modify-write operations within this process.

    The ledger retains its OS lock against competing processes. Only accounting
    is serialized; independent network requests can run concurrently.
    """
    def __init__(self, ledger):
        self.ledger = ledger
        self.lock = threading.RLock()

    def reserve(self, *args):
        with self.lock:
            return self.ledger.reserve(*args)

    def settle(self, *args):
        with self.lock:
            return self.ledger.settle(*args)

    def validate_reservations(self, *args):
        with self.lock:
            return self.ledger.validate_reservations(*args)

    def summary(self):
        with self.lock:
            return self.ledger.summary()


class _CoordinatedClient(BaseLLMClient):
    def __init__(self, client, stop):
        self.client = client
        self.stop = stop

    def preflight(self):
        # All clients were checked together before any generation began.
        if self.stop.is_set():
            raise LLMError("Collection stopped because another model failed.", retryable=True)

    def generate(self, prompt, *, seed=None):
        if self.stop.is_set():
            raise LLMError("Collection stopped because another model failed.", retryable=True)
        try:
            return self.client.generate(prompt, seed=seed)
        except LLMError as exc:
            if not exc.retryable:
                self.stop.set()
            raise


def model_configs(config):
    """Keep the total physical-request cap, assigning a fixed share per model."""
    cap, extra = divmod(config.max_requests, len(config.models))
    return tuple(replace(config, models=(model,), run_dir=config.run_dir / model.alias,
                         max_requests=cap + (index < extra))
                 for index, model in enumerate(config.models))


def run_multi_model(config, *, dry_run=False, max_workers=3,
                    client_factory=create_client, runner=run_experiment):
    if type(max_workers) is not int or max_workers < 1:
        raise ValueError("max_workers must be a positive integer.")
    configs = model_configs(config)
    plans = [runner(item, dry_run=True) for item in configs]
    if dry_run:
        return {"status": "dry_run", "planned_responses": sum(p["planned_responses"] for p in plans),
                "max_requests": config.max_requests,
                "max_concurrent_models": min(max_workers, len(configs)),
                "runs": plans, "run_dirs": [str(item.run_dir) for item in configs]}
    _validate_prerequisite(config)
    # Fail before any paid requests if any requested model is unavailable.
    clients = {model.alias: client_factory(model) for model in config.models}
    for client in clients.values():
        client.preflight()
    ledger = create_budget(config)
    budget = SerializedBudget(ledger) if ledger is not None else None
    stop = threading.Event()
    guarded = {alias: _CoordinatedClient(client, stop) for alias, client in clients.items()}
    specification = {
        "schema_version": 1, "config": config.to_dict(),
        "model_runs": [{"model": item.models[0].alias, "run_dir": str(item.run_dir),
                        "specification": build_plan(item)[0]} for item in configs],
        "ordering": "One independently shuffled durable run per model; shared experiment seed.",
    }
    metadata_path=config.dataset_path.with_name(config.dataset_path.stem+"_metadata.csv")
    if metadata_path.exists():
        specification["metadata_path"]=str(metadata_path)
        specification["metadata_sha256"]=hashlib.sha256(metadata_path.read_bytes()).hexdigest()
    specification["evaluator_version"]=evaluation.EVALUATOR_VERSION
    specification["evaluator_sha256"]=hashlib.sha256(Path(evaluation.__file__).read_bytes()).hexdigest()
    if config.dataset_path.stem=="claims_main":
        aliases_path=config.dataset_path.parent.parent/"verification"/"main_answer_aliases.json"
        specification["aliases_path"]=str(aliases_path)
        specification["aliases_sha256"]=hashlib.sha256(aliases_path.read_bytes()).hexdigest()
    manifest_path = config.run_dir / "collection_manifest.json"
    config.run_dir.mkdir(parents=True, exist_ok=True)
    if manifest_path.exists():
        import json
        if json.loads(manifest_path.read_text(encoding="utf-8")) != specification:
            raise ValueError("Multi-model collection specification changed; refusing unsafe resume.")
    else:
        _save_json(manifest_path, specification)

    def collect(item):
        try:
            result = runner(item, client_factory=lambda model: guarded[model.alias], budget=budget,
                            stop_event=stop, prerequisite_validated=True)
        except Exception:
            stop.set()
            raise
        if result.get("status") != "complete":
            stop.set()
        return result

    results, errors = {}, {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(configs))) as executor:
        futures = {executor.submit(collect, item): item.models[0].alias for item in configs}
        for future in as_completed(futures):
            alias = futures[future]
            try:
                results[alias] = future.result()
            except Exception as exc:
                # Generic exceptions can contain sensitive inputs. Log only type.
                errors[alias] = type(exc).__name__
                stop.set()
    summary = {
        "status": "complete" if not errors and all(r["status"] == "complete" for r in results.values()) else "incomplete",
        "planned_responses": sum(plan["planned_responses"] for plan in plans),
        "completed_responses": sum(r.get("completed_responses", 0) for r in results.values()),
        "models": dict(sorted(results.items())), "errors": errors,
        "budget": budget.summary() if budget else None,
    }
    _save_json(config.run_dir / "collection_summary.json", summary)
    return summary
