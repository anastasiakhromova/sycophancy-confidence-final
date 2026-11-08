"""Seeded, resumable inference with durable responses and physical-attempt accounting."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import time
from typing import Callable
import uuid

from .constants import PROMPT_TEMPLATE_VERSION
from .data import _atomic_text_file, load_claims
from .experiment_config import ExperimentConfig, ModelConfig
from .llm import BaseLLMClient, LLMError, LLMResponse, create_client
from .prompts import generate_prompts, validate_prompts
from .validation import validate_claims


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _hash(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _save_json(path: Path, value: object) -> None:
    with _atomic_text_file(path) as stream:
        stream.write(_json(value) + "\n")


def _append(path: Path, value: dict) -> None:
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(_json(value) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field")
        result[key] = value
    return result


def _parse_json(raw: bytes):
    return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON number")))


def _incomplete_fragment(raw: bytes, error: Exception) -> bool:
    """Recover syntax truncated at EOF, never complete invalid JSON objects."""
    if not raw.lstrip().startswith(b"{"):
        return False
    if isinstance(error, UnicodeDecodeError):
        return error.reason == "unexpected end of data"
    if not isinstance(error, json.JSONDecodeError):
        return False  # Duplicate fields and nonfinite numbers are corruption.
    text = raw.decode("utf-8").rstrip()
    if error.pos >= len(text) or error.msg.startswith("Unterminated string"):
        return True
    suffix = text[error.pos:]
    if suffix in {"t", "tr", "tru", "f", "fa", "fal", "fals", "n", "nu", "nul"}:
        return True
    # JSONDecoder accepts the complete numeric prefix before detecting a missing
    # decimal/exponent tail, so consider the entire final scalar token here.
    token = text.rsplit(":", 1)[-1].strip()
    return bool(re.fullmatch(r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]*)?(?:[eE][+-]?[0-9]*)?", token)
                and token[-1:] in ".eE+-")


def read_jsonl(path: str | Path, *, recover_tail: bool = False) -> list[dict]:
    """Reject corrupt complete lines; only an unterminated invalid final fragment is recoverable.

    Recovery retains the removed bytes in a .partial-* evidence file. Valid final
    JSON without a newline is preserved and terminated before a subsequent append.
    Call with recovery enabled only while holding the run lock.
    """
    path = Path(path)
    if not path.exists():
        return []
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    rows = []
    offset = 0
    for index, line in enumerate(lines):
        try:
            row = _parse_json(line)
        except (ValueError, UnicodeError) as exc:
            if recover_tail and index == len(lines) - 1 and not line.endswith(b"\n") and _incomplete_fragment(line, exc):
                backup = path.with_name(path.name + ".partial-" + uuid.uuid4().hex)
                with backup.open("xb") as stream:
                    stream.write(line)
                    stream.flush()
                    os.fsync(stream.fileno())
                with path.open("r+b") as stream:
                    stream.truncate(offset)
                    stream.flush()
                    os.fsync(stream.fileno())
                break
            raise ValueError(f"Corrupt JSONL history: {path.name} line {index + 1}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"JSONL row must be an object: {path.name} line {index + 1}")
        rows.append(row)
        offset += len(line)
    else:
        if recover_tail and raw and not raw.endswith(b"\n"):
            with path.open("ab") as stream:
                stream.write(b"\n")
                stream.flush()
                os.fsync(stream.fileno())
    return rows


@contextmanager
def _run_lock(run_dir: Path):
    """OS advisory lock, released automatically if the process crashes."""
    run_dir.mkdir(parents=True, exist_ok=True)
    stream = (run_dir / ".run.lock").open("a+b")
    try:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("Another process is using this experiment run directory.") from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def build_plan(config: ExperimentConfig) -> tuple[dict, list[dict]]:
    """Pure planning: validate data/prompts, select whole claims, shuffle request units."""
    dataset_bytes = config.dataset_path.read_bytes()
    claims, validation = validate_claims(load_claims(config.dataset_path))
    if config.dataset_path.read_bytes() != dataset_bytes:
        raise ValueError("Dataset changed while the experiment plan was being built.")
    if config.require_verified and any(not claim.verified for claim in claims):
        raise ValueError("This experiment requires every claim to be verified.")
    if config.sample_claims is not None:
        if config.sample_claims > len(claims):
            raise ValueError("sample_claims exceeds the dataset size.")
        claims = sorted(random.Random(config.seed).sample(claims, config.sample_claims), key=lambda claim: claim.claim_id)
    prompts = generate_prompts(claims)
    validate_prompts(prompts, claims, validation)
    plan = []
    for model in config.models:
        for repetition in range(1, config.repetitions + 1):
            for item in prompts:
                row = asdict(item)
                row["domain"] = item.domain.value
                row["confidence"] = item.confidence.value
                row.update(model=model.alias, model_id=model.model_id, provider=model.provider,
                           temperature=model.temperature, repetition=repetition,
                           reasoning_effort=model.reasoning_effort,
                           max_output_tokens=model.max_tokens,
                           generation_seed=model.seed + repetition - 1 if model.seed is not None else None)
                row["response_id"] = _hash([model.alias, item.experiment_item_id, repetition])[:24]
                plan.append(row)
    random.Random(config.seed).shuffle(plan)
    for order, row in enumerate(plan, start=1):
        row["request_order"] = order
    specification = {
        "schema_version": 1,
        "config": config.to_dict(),
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "prompt_template_version": PROMPT_TEMPLATE_VERSION,
        "prompt_plan_sha256": _hash(plan),
        "selected_claim_ids": [claim.claim_id for claim in claims],
        "claims": len(claims),
        "verified_claims": sum(claim.verified for claim in claims),
        "models": [model.model_id for model in config.models],
        "total_responses": len(plan),
    }
    return specification, plan


def _validate_response(row: dict, expected: dict, run_id: str) -> None:
    if row.get("run_id") != run_id or any(row.get(key) != value for key, value in expected.items()):
        raise ValueError("Response history contains a stale or changed request row.")
    if not isinstance(row.get("response"), str) or (not row["response"].strip() and row.get("status") != "incomplete"):
        raise ValueError("Response history contains empty/nontext model output.")
    for key in ("input_tokens", "output_tokens", "cached_input_tokens", "cache_write_tokens", "reasoning_tokens"):
        value = row.get(key)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError("Response history contains invalid token counts.")
    latency = row.get("latency")
    if latency is not None and (type(latency) not in (int, float) or not math.isfinite(latency) or latency < 0):
        raise ValueError("Response history contains invalid latency.")
    try:
        timestamp = datetime.fromisoformat(row["timestamp"])
        if timestamp.tzinfo is None:
            raise ValueError("Timezone absent")
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Response history contains an invalid timestamp.") from exc


def _history(config: ExperimentConfig, plan: list[dict], run_id: str):
    expected = {row["response_id"]: row for row in plan}
    responses = read_jsonl(config.run_dir / "responses.jsonl", recover_tail=True)
    successful = {}
    for row in responses:
        response_id = row.get("response_id")
        if response_id not in expected or response_id in successful:
            raise ValueError("Response history contains an unknown or duplicate response_id.")
        _validate_response(row, expected[response_id], run_id)
        successful[response_id] = row
    events = read_jsonl(config.run_dir / "attempts.jsonl", recover_tail=True)
    starts, endings, counts = {}, {}, Counter()
    terminal = set()
    for event in events:
        rid, aid, status = event.get("response_id"), event.get("attempt_id"), event.get("status")
        if event.get("run_id") != run_id or rid not in expected or type(aid) is not int:
            raise ValueError("Attempt history contains an unknown request/run/attempt.")
        if event.get("request_order") != expected[rid]["request_order"]:
            raise ValueError("Attempt history contains a stale request order.")
        try:
            if datetime.fromisoformat(event["timestamp"]).tzinfo is None:
                raise ValueError("Timezone absent")
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Attempt history contains an invalid timestamp.") from exc
        if status == "started":
            if aid != len(starts) + 1 or rid in terminal:
                raise ValueError("Attempt history has invalid start sequence.")
            starts[aid] = rid
            counts[rid] += 1
            if event.get("attempt_for_response") != counts[rid]:
                raise ValueError("Attempt history contains an invalid per-response attempt count.")
        elif status in {"succeeded", "failed"}:
            if starts.get(aid) != rid or aid in endings:
                raise ValueError("Attempt history has an unmatched or duplicate result.")
            endings[aid] = status
            if status == "succeeded":
                if rid not in successful:
                    raise ValueError("Attempt marked successful without a durable response.")
                terminal.add(rid)
            elif event.get("retryable") is not True:
                terminal.add(rid)
        else:
            raise ValueError("Attempt history contains an unknown status.")
    if len(starts) > config.max_requests or any(count > config.retries + 1 for count in counts.values()):
        raise ValueError("Attempt history exceeds immutable configured request/retry limits.")
    if any(not counts[rid] for rid in successful):
        raise ValueError("Response exists without a corresponding durable attempt start.")
    return successful, counts, len(starts), terminal


def validate_budget_history(run_dir: str | Path, budget_path: str | Path | None,
                            budget_limit_usd: float = 8.0, *, require_settled: bool = False,
                            relocate_paths: bool = False) -> dict | None:
    """Audit receipts across this run, model children, and predecessor runs.

    A new stage must not silently start a fresh ledger after older spending was
    lost. Summary-only prerequisites have no historical receipts to audit.
    Unknown billing remains visible in reports but cannot pass a cost gate.
    Offline reporting opts into relocation; paid resume retains exact paths.
    """
    from .budget import BudgetLedger, _locked, _money
    from .paths import resolve_recorded_path

    expected_path = Path(budget_path).resolve() if budget_path is not None else None
    visited: set[Path] = set()
    receipts: dict[str, tuple[tuple[str, str, int], str | None]] = {}

    def inspect(directory: Path) -> None:
        directory = directory.resolve()
        if directory in visited:
            return
        visited.add(directory)
        collection_path = directory / "collection_manifest.json"
        manifest_path = directory / "manifest.json"
        collection = _parse_json(collection_path.read_bytes()) if collection_path.exists() else None
        manifest = _parse_json(manifest_path.read_bytes()) if manifest_path.exists() else None
        specification = manifest.get("specification", {}) if manifest else {}
        settings = collection.get("config", {}) if collection else specification.get("config", {})
        def historical_path(value):
            return (resolve_recorded_path(value, settings.get("run_dir"), directory)
                    if relocate_paths else Path(value).resolve())

        prior_budget = settings.get("budget_path")
        if prior_budget is not None:
            if (expected_path is None or historical_path(prior_budget) != expected_path
                    or _money(settings.get("budget_limit_usd", 8.0)) != _money(budget_limit_usd)):
                raise ValueError("Historical run uses a different global budget ledger or limit.")
        events = read_jsonl(directory / "attempts.jsonl")
        records = read_jsonl(directory / "responses.jsonl")
        budgeted_history = prior_budget is not None or any(row.get("budget_reservation_id") for row in events + records)
        if budgeted_history:
            if expected_path is None:
                raise ValueError("Historical budget reservations require the same global budget ledger.")
            plan = {row["response_id"]: row for row in manifest.get("plan", [])} if manifest else {}
            summary_path = directory / "run_summary.json"
            if manifest and summary_path.exists():
                summary = _parse_json(summary_path.read_bytes())
                expected_attempts = summary.get("physical_attempts", 0)
                if (type(expected_attempts) is int
                        and expected_attempts > sum(event.get("status") == "started" for event in events)):
                    raise ValueError("Historical started budget reservation evidence is missing.")
            starts: dict[str, set[str]] = {}
            for event in events:
                if event.get("status") != "started":
                    continue
                reservation = event.get("budget_reservation_id")
                rid = event.get("response_id")
                if (not isinstance(reservation, str) or not reservation
                        or not isinstance(rid, str) or not rid):
                    raise ValueError("Historical started attempt is missing its budget reservation.")
                if manifest and (rid not in plan or event.get("run_id") != manifest.get("run_id")):
                    raise ValueError("Historical budget receipt belongs to a foreign request or run.")
                owner = (str(directory), rid, event.get("attempt_id"))
                if reservation in receipts:
                    raise ValueError("Historical attempts reuse a budget reservation.")
                receipts[reservation] = (owner, plan.get(rid, {}).get("model_id"))
                starts.setdefault(rid, set()).add(reservation)
            for row in records:
                if row.get("budget_reservation_id") not in starts.get(row.get("response_id"), set()):
                    raise ValueError("Historical response has no matching started budget reservation.")
        if collection:
            for child in collection.get("model_runs", []):
                child_path = historical_path(child["run_dir"])
                if relocate_paths and not (child_path / "manifest.json").is_file():
                    raise ValueError("Historical model manifest missing from the relocated collection.")
                inspect(child_path)
        predecessor = settings.get("prerequisite_run_dir")
        if predecessor is not None:
            predecessor_path = historical_path(predecessor)
            if relocate_paths and not any((predecessor_path / name).is_file()
                                         for name in ("manifest.json", "collection_manifest.json", "run_summary.json")):
                raise ValueError("Historical predecessor evidence missing from the relocated collection.")
            inspect(predecessor_path)

    inspect(Path(run_dir))
    if expected_path is None:
        return None
    # A real run with receipts must retain its ledger even when it is no longer
    # the run being resumed. Do not let BudgetLedger._read create a zero history.
    if receipts and not expected_path.exists():
        raise ValueError("Budget ledger missing despite historical requests; refusing to reset spending.")
    ledger = BudgetLedger(expected_path, budget_limit_usd)
    with _locked(ledger.lock_path):
        data = ledger._read()
        if any(reservation not in data["reservations"] for reservation in receipts):
            raise ValueError("Budget ledger does not contain every historical request reservation.")
        for reservation, (_, model_id) in receipts.items():
            if model_id is not None and data["reservations"][reservation].get("model_id") != model_id:
                raise ValueError("Budget reservation model differs from its historical request.")
        actual, unresolved = ledger._totals(data)
        overrun = any(entry.get("reserve_exceeded") for entry in data["reservations"].values())
        unknown = any(entry.get("actual_usd") is None for entry in data["reservations"].values())
        ready = not unknown and not overrun and actual <= ledger.limit
        historical_unknown = any(data["reservations"][receipt].get("actual_usd") is None for receipt in receipts)
        # Parallel model children recheck their predecessor while sibling calls
        # may be in flight. Only predecessor receipts must already be settled.
        if require_settled and (historical_unknown or overrun or actual + unresolved > ledger.limit):
            raise ValueError("Prerequisite cost review has unresolved billing or a budget overrun; audit required.")
        return {"limit_usd": float(ledger.limit), "observed_usage_cost_usd": float(actual),
                "unresolved_reserved_usd": float(unresolved), "remaining_usd": float(ledger.limit-actual-unresolved),
                "n_attempts": len(data["reservations"]), "pricing_date": data["pricing_date"],
                "cost_status": "usage-priced estimate; compare provider invoice",
                "historical_reservations_checked": len(receipts), "reserve_exceeded": bool(overrun),
                "review_ready": ready}


def _validate_prerequisite(config: ExperimentConfig) -> None:
    """Require a completed baseline and a matching explicit analysis/cost review."""
    prerequisite = config.prerequisite_run_dir
    if prerequisite is None:
        return
    try:
        summary = _parse_json((prerequisite / "run_summary.json").read_bytes())
        review = _parse_json((prerequisite / "cost_review.json").read_bytes())
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError("Prerequisite run must finish and have a valid cost_review.json before this experiment can run.") from exc
    if not isinstance(summary, dict) or not isinstance(review, dict):
        raise ValueError("Prerequisite summary and cost review must be JSON objects.")
    planned = summary.get("planned_responses")
    if (summary.get("status") != "complete" or type(planned) is not int or planned < 1
            or type(summary.get("completed_responses")) is not int
            or summary["completed_responses"] != planned):
        raise ValueError("Prerequisite run is not complete with every planned response completed.")
    run_id = summary.get("run_id")
    observed_cost = review.get("observed_usage_cost_usd")
    if (not isinstance(run_id, str) or not run_id or review.get("run_id") != run_id
            or review.get("status") != "reviewed"
            or type(review.get("expected_evaluable_responses")) is not int
            or review["expected_evaluable_responses"] != planned
            or type(observed_cost) not in (int, float) or not math.isfinite(observed_cost) or observed_cost < 0):
        raise ValueError("Prerequisite cost review is missing, stale, or does not cover every planned response.")
    validate_budget_history(prerequisite, config.budget_path, config.budget_limit_usd, require_settled=True)


def run_experiment(
    config: ExperimentConfig, *, dry_run: bool = False,
    client_factory: Callable[[ModelConfig], BaseLLMClient] = create_client,
    sleep: Callable[[float], None] = time.sleep,
    budget=None, stop_event=None, prerequisite_validated: bool = False,
) -> dict:
    """Run real clients, or plan without creating clients, files, or network calls.

    max_requests limits physical attempts across the entire run, including retries
    and interrupted in-flight requests. Both that cap and retry limits are immutable
    on resume. A lost in-flight request can be retried within the remaining budget;
    completed, durable responses are never sent again. Remote exactly-once execution
    is impossible without provider support for idempotency.
    """
    specification, plan = build_plan(config)
    if dry_run:
        result = {"status": "dry_run", "planned_responses": len(plan), "claims": specification["claims"],
                "max_requests": config.max_requests, "request_order": [row["response_id"] for row in plan],
                "dataset_sha256": specification["dataset_sha256"], "run_dir": str(config.run_dir)}
        if config.budget_path is not None:
            from .budget import estimate_cost
            models = {model.alias: model for model in config.models}
            upper = sum(estimate_cost(models[row["model"]], row["prompt"]) for row in plan)
            result.update(budget_limit_usd=config.budget_limit_usd,
                          maximum_cost_without_retries_usd=upper,
                          maximum_cost_with_all_retries_usd=upper * (config.retries + 1))
        return result
    if not prerequisite_validated:
        _validate_prerequisite(config)
    with _run_lock(config.run_dir):
        if any(model.model_id.startswith("REPLACE_WITH_") or "example.test" in model.base_url for model in config.models):
            raise ValueError("Replace example provider URLs and explicit model IDs in the config before a real run.")
        manifest_path = config.run_dir / "manifest.json"
        if manifest_path.exists():
            manifest = _parse_json(manifest_path.read_bytes())
            if not isinstance(manifest, dict) or manifest.get("specification") != specification or manifest.get("plan") != plan:
                raise ValueError("Resume rejected: config, dataset, or prompt manifest has changed.")
            run_id = manifest.get("run_id")
            if not isinstance(run_id, str) or len(run_id) != 36:
                raise ValueError("Invalid run ID in manifest.")
        else:
            if any((config.run_dir / filename).exists() for filename in ("responses.jsonl", "attempts.jsonl")):
                raise ValueError("Cannot adopt response/attempt history without its original manifest.")
            run_id = str(uuid.uuid4())
            _save_json(manifest_path, {"run_id": run_id, "created_at": _timestamp(),
                                      "specification": specification, "plan": plan})
        successful, counts, attempts, terminal = _history(config, plan, run_id)
        if budget is None and config.budget_path is not None:
            from .budget import create_budget
            budget = create_budget(config)
        if budget is not None and attempts:
            historical_starts = [event for event in read_jsonl(config.run_dir / "attempts.jsonl")
                                 if event["status"] == "started"]
            reservations = [event.get("budget_reservation_id") for event in historical_starts]
            if any(not isinstance(reservation, str) or not reservation for reservation in reservations):
                raise ValueError("Budgeted run history contains a request without its original budget reservation.")
            budget.validate_reservations(reservations)
            for rid, row in successful.items():
                matching = {event["budget_reservation_id"] for event in historical_starts if event["response_id"] == rid}
                if row.get("budget_reservation_id") not in matching:
                    raise ValueError("Saved response has a stale or missing budget reservation pointer.")
        pending = [row for row in plan if row["response_id"] not in successful]
        aliases_needed = {row["model"] for row in pending if row["response_id"] not in terminal
                          and counts[row["response_id"]] < config.retries + 1}
        clients = {model.alias: client_factory(model) for model in config.models
                   if model.alias in aliases_needed and attempts < config.max_requests}
        for client in clients.values():
            client.preflight()
        models_by_alias = {model.alias: model for model in config.models}
        responses_path, attempts_path = config.run_dir / "responses.jsonl", config.run_dir / "attempts.jsonl"
        interrupted = False
        cost_limit_reached = False
        fatal_error = None
        try:
            for request in pending:
                rid = request["response_id"]
                if rid in terminal:
                    continue
                while counts[rid] < config.retries + 1 and attempts < config.max_requests:
                    if stop_event is not None and stop_event.is_set():
                        interrupted = True
                        break
                    if counts[rid]:
                        sleep(config.backoff_seconds * 2 ** (counts[rid] - 1))
                    if stop_event is not None and stop_event.is_set():
                        interrupted = True
                        break
                    reservation = None
                    if budget is not None:
                        from .budget import BudgetExceeded
                        try:
                            reservation = budget.reserve(models_by_alias[request["model"]], request["prompt"])
                        except BudgetExceeded:
                            cost_limit_reached = True
                            break
                    attempts += 1
                    counts[rid] += 1
                    event = {"run_id": run_id, "response_id": rid, "attempt_id": attempts,
                             "request_order": request["request_order"], "attempt_for_response": counts[rid],
                             "budget_reservation_id": reservation}
                    _append(attempts_path, {**event, "status": "started", "timestamp": _timestamp()})
                    started = time.perf_counter()
                    try:
                        result = clients[request["model"]].generate(request["prompt"], seed=request["generation_seed"])
                        if not isinstance(result, LLMResponse):
                            raise LLMError("Client returned an invalid response object")
                        row = {**request, "run_id": run_id, "response": result.text,
                               "timestamp": _timestamp(), "input_tokens": result.input_tokens,
                               "output_tokens": result.output_tokens,
                               "latency": result.latency if result.latency is not None else time.perf_counter() - started,
                               "provider_model": result.provider_model, "finish_reason": result.finish_reason,
                               "system_fingerprint": result.system_fingerprint,
                               "cached_input_tokens": result.cached_input_tokens, "cache_write_tokens": result.cache_write_tokens,
                               "reasoning_tokens": result.reasoning_tokens, "provider_response_id": result.provider_response_id,
                               "service_tier": result.service_tier, "status": result.status,
                               "incomplete_reason": result.incomplete_reason, "budget_reservation_id": reservation}
                        _validate_response(row, request, run_id)
                    except LLMError as exc:
                        _append(attempts_path, {**event, "status": "failed", "timestamp": _timestamp(),
                                               "error_type": type(exc).__name__, "http_status": exc.status,
                                               "error_message": str(exc) if exc.safe_to_log else type(exc).__name__,
                                               "retryable": exc.retryable})
                        if exc.status in {401, 403, 404}:
                            fatal_error = str(exc)
                        if not exc.retryable:
                            terminal.add(rid)
                            break
                        continue
                    _append(responses_path, row)  # Persist success before any further work.
                    successful[rid] = row
                    if budget is not None:
                        try:
                            budget.settle(reservation, result)
                        except (BudgetExceeded, ValueError) as exc:
                            fatal_error = f"Budget settlement stopped the run: {exc}"
                    _append(attempts_path, {**event, "status": "succeeded", "timestamp": _timestamp()})
                    break
                if cost_limit_reached or fatal_error or interrupted:
                    break
        except KeyboardInterrupt:
            interrupted = True
        remaining = len(plan) - len(successful)
        status = "budget_exhausted" if cost_limit_reached else "stopped" if fatal_error else "complete" if remaining == 0 else "interrupted" if interrupted else "incomplete"
        summary = {"run_id": run_id, "status": status, "planned_responses": len(plan),
                   "successful_responses": len(successful), "remaining_responses": remaining,
                   "completed_responses": sum(row.get("status", "completed") == "completed" for row in successful.values()),
                   "incomplete_responses": sum(row.get("status") == "incomplete" for row in successful.values()),
                   "physical_attempts": attempts, "max_requests": config.max_requests,
                   "budget_exhausted": attempts >= config.max_requests and remaining > 0,
                   "cost_limit_reached": cost_limit_reached, "fatal_error": fatal_error,
                   "timestamp": _timestamp(), "run_dir": str(config.run_dir)}
        if budget is not None:
            summary["budget"] = budget.summary()
        _save_json(config.run_dir / "run_summary.json", summary)
        return summary
