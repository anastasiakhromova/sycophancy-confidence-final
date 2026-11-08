"""Separate, frozen challenge collection; no original-study files are written.

The 30-claim plan is fixed before inference: knowledge controls first, then all
360 assertion prompts. Knowledge outcomes never select or remove claims.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import random
import time
import tomllib
import uuid

from .budget import BudgetExceeded, BudgetLedger, PRICES, estimate_cost, usage_cost
from .experiment_config import ModelConfig
from .llm import LLMError, LLMResponse, OpenAIResponsesClient
from .runner import (_append, _hash, _history, _parse_json, _run_lock, _save_json,
                     _timestamp, _validate_response, read_jsonl)


CONFIDENCES = ("low", "neutral", "high")
FAMILIES = ("A", "B", "C")
DOMAINS = ("geography", "history", "science", "technology", "general_knowledge")
ORIGINAL_SPENT = Decimal("1.3652759")
GLOBAL_CAP = Decimal("8")
CHALLENGE_CAP = Decimal("0.50")


@dataclass(frozen=True)
class ChallengeConfig:
    project: Path
    config_path: Path
    claims_path: Path
    cues_path: Path
    protocol_path: Path
    run_dir: Path
    budget_path: Path
    model: ModelConfig
    seed: int = 20261024
    max_requests: int = 780
    retries: int = 1
    backoff_seconds: float = 2.0
    budget_limit_usd: float = 0.50

    def to_dict(self):
        return {key: str(value) if isinstance(value, Path) else value
                for key, value in asdict(self).items()}


def load_challenge_config(path):
    path = Path(path).resolve()
    project = path.parent.parent
    values = tomllib.loads(path.read_text(encoding="utf-8"))
    known = {"claims_path", "cues_path", "protocol_path", "run_dir", "budget_path",
             "seed", "max_requests", "retries", "backoff_seconds", "budget_limit_usd", "model"}
    if set(values) - known:
        raise ValueError("Unknown challenge configuration fields.")
    for name in ("claims_path", "cues_path", "protocol_path", "run_dir", "budget_path"):
        value = values.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Missing challenge path: " + name)
        values[name] = (path.parent / value).resolve()
        if not values[name].is_relative_to(project / "data/challenge_v1"):
            raise ValueError("Challenge paths must stay inside data/challenge_v1: " + name)
    if values["budget_path"] != values["run_dir"] / "budget.json":
        raise ValueError("Challenge ledger must be run_dir/budget.json.")
    if any(p == values["run_dir"] or p.is_relative_to(values["run_dir"])
           for p in (values["claims_path"], values["cues_path"], values["protocol_path"])):
        raise ValueError("Frozen sources must be outside the writable run directory.")
    model_values = dict(values.pop("model", {}))
    model_values.setdefault("temperature", None)
    model_values["base_url"] = os.environ.get("OPENAI_BASE_URL", model_values.get("base_url", "https://api.openai.com/v1"))
    model = ModelConfig(**model_values)
    if (model.model_id != "gpt-6-luna" or model.alias != "gpt-6-luna"
            or model.provider != "openai-responses" or model.temperature is not None
            or model.reasoning_effort != "low" or model.max_tokens != 512 or model.seed is not None):
        raise ValueError("Challenge requires exact gpt-6-luna, Responses API, low effort, 512 output tokens and no sampling overrides.")
    config = ChallengeConfig(project=project, config_path=path, model=model, **values)
    if (type(config.seed) is not int or config.seed < 0
            or type(config.retries) is not int or not 0 <= config.retries <= 2
            or type(config.max_requests) is not int or not 390 <= config.max_requests <= 390 * (config.retries + 1)):
        raise ValueError("Invalid fixed request or retry limits.")
    cap = Decimal(str(config.budget_limit_usd))
    if not cap.is_finite() or not 0 < cap <= min(CHALLENGE_CAP, GLOBAL_CAP - ORIGINAL_SPENT):
        raise ValueError("Challenge cap must be positive and at most $0.50 within the original $8 guard.")
    if (type(config.backoff_seconds) not in (int, float)
            or not 0 <= config.backoff_seconds <= 60):
        raise ValueError("Invalid retry backoff.")
    return config


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _source_files(config):
    paths = [config.config_path, config.claims_path, config.cues_path, config.protocol_path,
             config.project / "data/runs/budget.json"]
    for relative in ("src/sycophancy/challenge.py", "src/sycophancy/llm.py",
                     "src/sycophancy/budget.py", "src/sycophancy/runner.py",
                     "src/sycophancy/experiment_config.py", "scripts/run_challenge.py"):
        candidate = config.project / relative
        if candidate.is_file():
            paths.append(candidate)
    return {path.relative_to(config.project).as_posix(): _digest(path) for path in paths}


def _original_budget(config):
    # Read directly: constructing the old ledger would create its lock file.
    old = _parse_json((config.project / "data/runs/budget.json").read_bytes())
    entries = old.get("reservations", {})
    spent = sum((Decimal(str(row["actual_usd"])) for row in entries.values()
                 if row.get("actual_usd") is not None), Decimal(0))
    pending = sum((Decimal(str(row["reserved_usd"])) for row in entries.values()
                   if row.get("actual_usd") is None), Decimal(0))
    if spent != ORIGINAL_SPENT or pending != 0 or Decimal(str(old["limit_usd"])) != GLOBAL_CAP:
        raise ValueError("Original-study budget differs from the frozen $1.3652759 settled cost and $8 guard.")
    return {"original_observed_usage_cost_usd": float(spent), "original_pending_usd": float(pending),
            "global_cap_usd": float(GLOBAL_CAP), "challenge_cap_usd": config.budget_limit_usd,
            "maximum_combined_observed_and_reserved_usd": float(spent + Decimal(str(config.budget_limit_usd))),
            "note": "Usage-priced estimate, not a provider invoice. Original ledger is read-only."}


def build_challenge_plan(config):
    cap = Decimal(str(config.budget_limit_usd))
    if not cap.is_finite() or not 0 < cap <= min(CHALLENGE_CAP, GLOBAL_CAP - ORIGINAL_SPENT):
        raise ValueError("Challenge spending cap exceeds the fixed authorization.")
    if (config.budget_path != config.run_dir / "budget.json"
            or not config.run_dir.is_relative_to(config.project / "data/challenge_v1")):
        raise ValueError("Challenge output and ledger must remain isolated from the original study.")
    if (config.model.model_id != "gpt-6-luna" or config.model.provider != "openai-responses"
            or config.model.max_tokens != 512 or config.model.reasoning_effort != "low"
            or config.model.temperature is not None or config.model.seed is not None):
        raise ValueError("Challenge model settings differ from the authorized fixed design.")
    hashes = _source_files(config)
    budget_context = _original_budget(config)
    claims = read_jsonl(config.claims_path)
    if len(claims) != 30 or len({row.get("claim_id") for row in claims}) != 30:
        raise ValueError("Challenge must contain exactly 30 unique claims.")
    if Counter(row.get("domain") for row in claims) != Counter({domain: 6 for domain in DOMAINS}):
        raise ValueError("Challenge requires six claims in each of the five fixed domains.")
    required = ("claim_id", "domain", "false_claim", "true_claim", "knowledge_question", "true_answer",
                "false_answer", "source_url", "source_title", "source_evidence", "rationale")
    for claim in claims:
        if any(not isinstance(claim.get(key), str) or not claim[key].strip() for key in required):
            raise ValueError("Missing or invalid challenge claim text.")
        for field in ("true_aliases", "false_aliases"):
            if (not isinstance(claim.get(field), list) or not claim[field]
                    or any(not isinstance(text, str) or not text.strip() for text in claim[field])):
                raise ValueError("Claim aliases must be nonempty string arrays.")
        if claim["false_claim"].strip() == claim["true_claim"].strip():
            raise ValueError("True and false control statements must differ.")
    cues = _parse_json(config.cues_path.read_bytes())
    families = cues.get("families", {})
    instruction = cues.get("assessment_instruction")
    knowledge_instruction = cues.get("knowledge_instruction", "")
    if not isinstance(knowledge_instruction, str):
        raise ValueError("knowledge_instruction must be text when supplied.")
    if set(families) != set(FAMILIES) or not isinstance(instruction, str) or not instruction.strip():
        raise ValueError("Cues require families A/B/C and an assessment_instruction.")
    for family in FAMILIES:
        if (set(families[family]) != set(CONFIDENCES)
                or any(not isinstance(text, str) or not text.strip() for text in families[family].values())):
            raise ValueError("Each cue family requires low, neutral and high text.")
    knowledge, assertions = [], []
    for claim in sorted(claims, key=lambda row: row["claim_id"]):
        common = {"claim_id": claim["claim_id"], "domain": claim["domain"],
                  "model": config.model.alias, "model_id": config.model.model_id,
                  "reasoning_effort": "low", "max_output_tokens": 512,
                  "generation_seed": None, "claim_sha256": _hash(claim)}
        knowledge.append({**common, "task": "knowledge", "cue_family": None, "confidence": "neutral",
                          "prompt": claim["knowledge_question"] + ("\n" + knowledge_instruction if knowledge_instruction else "")})
        for family in FAMILIES:
            for confidence in CONFIDENCES:
                assertions.append({**common, "task": "false_assertion", "cue_family": family,
                                   "confidence": confidence,
                                   "prompt": families[family][confidence] + "\n" + claim["false_claim"] + "\n" + instruction})
        for confidence in CONFIDENCES:
            assertions.append({**common, "task": "true_control", "cue_family": "A", "confidence": confidence,
                               "prompt": families["A"][confidence] + "\n" + claim["true_claim"] + "\n" + instruction})
    random.Random(config.seed).shuffle(knowledge)
    random.Random(config.seed + 1).shuffle(assertions)
    plan = knowledge + assertions
    for index, row in enumerate(plan, 1):
        row["request_order"] = index
        row["response_id"] = _hash([row["claim_id"], row["task"], row["cue_family"], row["confidence"], row["model_id"]])[:24]
        row["prompt_sha256"] = hashlib.sha256(row["prompt"].encode("utf-8")).hexdigest()
    if hashes != _source_files(config):
        raise ValueError("Challenge sources changed while building the plan.")
    specification = {"schema_version": 1, "study": "challenge_v1", "config": config.to_dict(),
                     "source_sha256": hashes, "plan_sha256": _hash(plan), "claims": 30,
                     "planned_responses": 390, "design_counts": dict(Counter(row["task"] for row in plan)),
                     "knowledge_outcome_filtering": False, "budget_context": budget_context,
                     "prices": PRICES[config.model.model_id]}
    return specification, plan


class ChallengeResponsesClient(OpenAIResponsesClient):
    """Preserve successful provider response envelopes alongside parsed outputs."""
    last_raw_response = None

    def _request(self, endpoint, body=None):
        if endpoint == "/responses":
            self.last_raw_response = None
        result = super()._request(endpoint, body)
        if endpoint == "/responses":
            self.last_raw_response = result
        return result


def _freeze(config, specification, plan):
    path = config.run_dir / "manifest.json"
    if path.exists():
        manifest = _parse_json(path.read_bytes())
        if manifest.get("specification") != specification or manifest.get("plan") != plan:
            raise ValueError("Challenge resume rejected: frozen configuration, source, code or plan changed.")
        if not isinstance(manifest.get("run_id"), str) or len(manifest["run_id"]) != 36:
            raise ValueError("Invalid challenge run identity.")
        return manifest
    if any((config.run_dir / name).exists() for name in ("responses.jsonl", "attempts.jsonl", "budget.json")):
        raise ValueError("Cannot adopt challenge request history without its immutable manifest.")
    manifest = {"run_id": str(uuid.uuid4()), "created_at": _timestamp(),
                "specification": specification, "plan": plan}
    _save_json(path, manifest)
    return manifest


def _budget_summary_readonly(config):
    ledger = BudgetLedger(config.budget_path, config.budget_limit_usd)
    data = ledger._read()
    actual, pending = ledger._totals(data)
    return {"limit_usd": config.budget_limit_usd, "observed_usage_cost_usd": float(actual),
            "unresolved_reserved_usd": float(pending), "remaining_usd": float(ledger.limit - actual - pending),
            "n_attempts": len(data["reservations"]),
            "combined_original_and_challenge_observed_usd": float(ORIGINAL_SPENT + actual),
            "cost_status": "Usage-priced estimate; unknown billing remains reserved."}


def challenge_status(config, specification=None, plan=None):
    specification, plan = (specification, plan) if plan is not None else build_challenge_plan(config)
    path = config.run_dir / "manifest.json"
    if not path.exists():
        return {"status": "not_started", "planned_responses": len(plan), "budget": _budget_summary_readonly(config)}
    manifest = _parse_json(path.read_bytes())
    if manifest.get("specification") != specification or manifest.get("plan") != plan:
        raise ValueError("Status rejected: frozen challenge inputs changed.")
    rows = read_jsonl(config.run_dir / "responses.jsonl")
    expected = {row["response_id"]: row for row in plan}
    seen = set()
    for row in rows:
        rid = row.get("response_id")
        if rid not in expected or rid in seen:
            raise ValueError("Duplicate or foreign challenge response.")
        _validate_response(row, expected[rid], manifest["run_id"])
        if row.get("response_sha256") != hashlib.sha256(row["response"].encode("utf-8")).hexdigest():
            raise ValueError("Saved challenge response text hash changed.")
        seen.add(rid)
    completed = sum(row.get("status") == "completed" and bool(row["response"].strip()) for row in rows)
    status = "complete" if completed == len(plan) else "incomplete" if rows else "prepared"
    return {"status": status, "run_id": manifest["run_id"], "planned_responses": len(plan),
            "recorded_responses": len(rows), "completed_responses": completed,
            "incomplete_or_failed_responses": len(rows) - completed,
            "missing_responses": len(plan) - len(rows),
            "recorded_by_task": dict(Counter(row["task"] for row in rows)),
            "budget": _budget_summary_readonly(config), "knowledge_outcome_filtering": False,
            "semantic_labels_created": False}


def run_challenge(config, *, dry_run=False, prepare=False, preflight=False, status_only=False,
                  max_new_requests=None, client_factory=ChallengeResponsesClient, sleep=time.sleep):
    specification, plan = build_challenge_plan(config)
    if dry_run:
        upper = sum(estimate_cost(config.model, row["prompt"]) for row in plan)
        return {"status": "dry_run", **specification, "run_dir": str(config.run_dir),
                "maximum_cost_without_retries_usd": upper,
                "maximum_cost_all_retries_usd": upper * (config.retries + 1),
                "request_order": [row["response_id"] for row in plan], "network_calls": 0}
    if status_only:
        return challenge_status(config, specification, plan)
    if max_new_requests is not None and (type(max_new_requests) is not int or max_new_requests < 0):
        raise ValueError("max_new_requests must be a nonnegative integer.")
    with _run_lock(config.run_dir):
        manifest = _freeze(config, specification, plan)
        if prepare:
            return {"status": "prepared", "run_id": manifest["run_id"], "plan_sha256": specification["plan_sha256"],
                    "planned_responses": len(plan), "network_calls": 0}
        run_id = manifest["run_id"]
        saved, counts, attempts, terminal = _history(config, plan, run_id)
        ledger = BudgetLedger(config.budget_path, config.budget_limit_usd)
        starts = [event for event in read_jsonl(config.run_dir / "attempts.jsonl") if event["status"] == "started"]
        ledger.validate_reservations([event.get("budget_reservation_id") for event in starts])
        for rid, row in saved.items():
            reservations = {event["budget_reservation_id"] for event in starts if event["response_id"] == rid}
            if row.get("budget_reservation_id") not in reservations:
                raise ValueError("Saved challenge response lacks its original budget reservation.")
            if row.get("response_sha256") != hashlib.sha256(row["response"].encode("utf-8")).hexdigest():
                raise ValueError("Saved challenge response hash changed.")
            # A crash after saving a response must not lose its settlement.
            fields = {key: row.get(key) for key in LLMResponse.__dataclass_fields__ if key != "text"}
            ledger.settle(row["budget_reservation_id"], LLMResponse(text=row["response"], **fields))
        pending = [row for row in plan if row["response_id"] not in saved
                   and row["response_id"] not in terminal and counts[row["response_id"]] < config.retries + 1]
        if not pending or attempts >= config.max_requests or max_new_requests == 0:
            return challenge_status(config, specification, plan)
        client = client_factory(config.model)
        client.preflight()
        if preflight:
            return {"status": "preflight_ok", "model_id": config.model.model_id,
                    "planned_responses": len(plan), "generation_calls": 0}
        new_attempts, stop_reason = 0, None
        try:
            for request in pending:
                rid = request["response_id"]
                while counts[rid] < config.retries + 1 and attempts < config.max_requests:
                    if max_new_requests is not None and new_attempts >= max_new_requests:
                        stop_reason = "requested_stop"
                        break
                    if counts[rid]:
                        sleep(config.backoff_seconds * 2 ** (counts[rid] - 1))
                    try:
                        reservation = ledger.reserve(config.model, request["prompt"])
                    except BudgetExceeded:
                        stop_reason = "budget_exhausted"
                        break
                    attempts += 1
                    new_attempts += 1
                    counts[rid] += 1
                    event = {"run_id": run_id, "response_id": rid, "attempt_id": attempts,
                             "request_order": request["request_order"], "attempt_for_response": counts[rid],
                             "budget_reservation_id": reservation}
                    _append(config.run_dir / "attempts.jsonl", {**event, "status": "started", "timestamp": _timestamp()})
                    try:
                        result = client.generate(request["prompt"], seed=None)
                        if not isinstance(result, LLMResponse):
                            raise LLMError("Invalid challenge response object")
                        if (not isinstance(result.text, str)
                                or result.status not in {"completed", "incomplete", "failed", "cancelled"}):
                            raise LLMError("Invalid challenge response text or status")
                        metadata = asdict(result)
                        text = metadata.pop("text")
                        row = {**request, **metadata, "response": text, "run_id": run_id,
                               "timestamp": _timestamp(), "budget_reservation_id": reservation,
                               "provider_raw_response": getattr(client, "last_raw_response", None),
                               "response_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                               "observed_usage_cost_usd": None}
                        _validate_response(row, request, run_id)
                        if (result.input_tokens is not None and result.output_tokens is not None
                                and result.service_tier in {None, "default", "standard"}):
                            row["observed_usage_cost_usd"] = float(usage_cost(config.model.model_id,
                                result.input_tokens, result.output_tokens, result.cached_input_tokens or 0,
                                result.cache_write_tokens or 0))
                    except (LLMError, ValueError, TypeError) as exc:
                        # Do not log provider bodies, prompts or arbitrary exception messages.
                        _append(config.run_dir / "attempts.jsonl", {**event, "status": "failed", "timestamp": _timestamp(),
                            "error_type": type(exc).__name__, "http_status": getattr(exc, "status", None),
                            "retryable": getattr(exc, "retryable", False),
                            "error_message": "Provider request failed; billing may be unknown."})
                        if getattr(exc, "status", None) in {401, 403, 404}:
                            stop_reason = "provider_unavailable_or_unauthorized"
                        if not getattr(exc, "retryable", False) or stop_reason:
                            break
                        continue
                    _append(config.run_dir / "responses.jsonl", row)
                    saved[rid] = row
                    try:
                        ledger.settle(reservation, result)
                    except (BudgetExceeded, ValueError):
                        stop_reason = "budget_settlement_requires_audit"
                    _append(config.run_dir / "attempts.jsonl", {**event, "status": "succeeded", "timestamp": _timestamp()})
                    break
                if stop_reason:
                    break
        except KeyboardInterrupt:
            stop_reason = "interrupted"
        summary = challenge_status(config, specification, plan)
        summary.update(new_physical_attempts=new_attempts, physical_attempts=attempts,
                       max_requests=config.max_requests, stop_reason=stop_reason, timestamp=_timestamp())
        if stop_reason:
            summary["status"] = stop_reason
        _save_json(config.run_dir / "run_summary.json", summary)
        return summary
