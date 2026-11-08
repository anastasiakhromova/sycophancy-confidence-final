"""Durable global budget reservations across runs, retries, and interruptions.

Rates are a dated Standard short-context snapshot, not an account invoice.
Reasoning is included in output_tokens and must never be charged a second time.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
import math
from pathlib import Path
from typing import Iterator
import uuid

from .data import _atomic_text_file

PRICING_DATE = "2026-10-06"
PRICING_SOURCE = "https://developers.openai.com/api/docs/pricing"
PRICES = {
    "gpt-6-luna": {"input": "0.10", "cached_input": "0.01", "cache_write": "0.125", "output": "0.50"},
    "gpt-6.1-sol": {"input": "2.00", "cached_input": "0.10", "cache_write": "2.50", "output": "10.00"},
    "gpt-6-astra": {"input": "10.00", "cached_input": "1.00", "cache_write": "12.50", "output": "50.00"},
}


class BudgetExceeded(RuntimeError):
    """A request is refused before submission because its reserve cannot fit."""


def _money(value: object) -> Decimal:
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise ValueError("Costs and budget limits must be finite and nonnegative.")
    return result


def usage_cost(model_id: str, input_tokens: int, output_tokens: int,
               cached_input_tokens: int = 0, cache_write_tokens: int = 0) -> Decimal:
    """Price disjoint input/cache categories and inclusive output-token usage."""
    rates = PRICES[model_id]
    for value in (input_tokens, output_tokens, cached_input_tokens, cache_write_tokens):
        if type(value) is not int or value < 0:
            raise ValueError("Usage token counts must be nonnegative integers.")
    if cached_input_tokens + cache_write_tokens > input_tokens:
        raise ValueError("Input cache subcategories exceed total input tokens.")
    regular = input_tokens - cached_input_tokens - cache_write_tokens
    return (regular * Decimal(rates["input"]) + cached_input_tokens * Decimal(rates["cached_input"])
            + cache_write_tokens * Decimal(rates["cache_write"]) + output_tokens * Decimal(rates["output"])) / 1_000_000


def estimate_cost(model_config, prompt: str) -> float:
    """Conservative reserve: UTF-8 bytes + 1024 structural tokens, full output cap.

    This is not an exact tokenizer count. It deliberately over-reserves for short
    plain-text, tool-free requests; unexpected excess usage stops subsequent calls.
    """
    if model_config.model_id not in PRICES:
        raise ValueError(f"No verified price snapshot for model {model_config.model_id}; refusing paid calls.")
    rates = PRICES[model_config.model_id]
    input_bound = len(prompt.encode("utf-8")) + 1024
    input_rate = max(Decimal(rates["input"]), Decimal(rates["cache_write"]))
    return float((input_bound * input_rate + model_config.max_tokens * Decimal(rates["output"])) / 1_000_000)


@contextmanager
def _locked(path: Path) -> Iterator[None]:
    """OS-owned nonblocking file lock; a crash cannot leave a stale held lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if stream.tell() == 0:
            stream.write(b"0")
            stream.flush()
        stream.seek(0)
        if __import__("os").name == "nt":
            import msvcrt
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("Global budget ledger is locked by another process.") from exc
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("Global budget ledger is locked by another process.") from exc
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class BudgetLedger:
    def __init__(self, path: str | Path, limit_usd: float = 8.0):
        self.path = Path(path).resolve()
        self.limit = _money(limit_usd)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def _read(self) -> dict:
        if not self.path.exists():
            return {"schema": 1, "limit_usd": str(self.limit), "pricing_date": PRICING_DATE,
                    "pricing_source": PRICING_SOURCE, "prices": PRICES, "reservations": {}}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if value.get("schema") != 1 or _money(value["limit_usd"]) != self.limit or value.get("prices") != PRICES:
            raise ValueError("Budget ledger settings or pricing changed; refusing to reset spent money.")
        for entry in value["reservations"].values():
            _money(entry["reserved_usd"])
            if entry.get("actual_usd") is not None:
                _money(entry["actual_usd"])
        return value

    def _write(self, value: dict) -> None:
        with _atomic_text_file(self.path) as stream:
            json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")

    @staticmethod
    def _totals(value: dict) -> tuple[Decimal, Decimal]:
        actual, reserved = Decimal(0), Decimal(0)
        for entry in value["reservations"].values():
            if entry.get("actual_usd") is None:
                reserved += _money(entry["reserved_usd"])
            else:
                actual += _money(entry["actual_usd"])
        return actual, reserved

    def reserve(self, model_config, prompt: str) -> str:
        amount = _money(estimate_cost(model_config, prompt))
        with _locked(self.lock_path):
            data = self._read()
            if any(entry.get("reserve_exceeded") for entry in data["reservations"].values()):
                raise BudgetExceeded("Budget ledger has an unresolved reservation overrun; audit required before resuming.")
            actual, pending = self._totals(data)
            if actual + pending + amount > self.limit:
                raise BudgetExceeded(f"Budget guard: ${actual + pending:.6f} used/reserved + ${amount:.6f} request reserve exceeds ${self.limit}.")
            reservation = uuid.uuid4().hex
            data["reservations"][reservation] = {
                "model_id": model_config.model_id, "reserved_usd": str(amount), "actual_usd": None,
                "timestamp": datetime.now(timezone.utc).isoformat(), "status": "reserved_or_unknown_billing",
            }
            self._write(data)
            return reservation

    def validate_reservations(self, ids) -> None:
        """Fail closed when a prior run's budget evidence is lost or replaced."""
        ids = list(ids)
        if not ids:
            return
        with _locked(self.lock_path):
            if not self.path.exists():
                raise ValueError("Budget ledger missing despite historical requests; refusing to reset spending.")
            data = self._read()
            if any(not isinstance(rid,str) or rid not in data["reservations"] for rid in ids):
                raise ValueError("Budget ledger does not contain every historical request reservation.")

    def settle(self, reservation: str, response) -> float | None:
        """Reconcile observed usage; absent usage leaves its reservation in place."""
        with _locked(self.lock_path):
            data = self._read()
            entry = data["reservations"][reservation]
            if response.input_tokens is None or response.output_tokens is None:
                return None
            if getattr(response, "service_tier", None) not in {None, "default", "standard"}:
                raise ValueError("Unexpected non-Standard service tier; billing cannot be reconciled safely.")
            cached = getattr(response, "cached_input_tokens", 0) or 0
            writes = getattr(response, "cache_write_tokens", 0) or 0
            actual = usage_cost(entry["model_id"], response.input_tokens, response.output_tokens, cached, writes)
            if entry["actual_usd"] is not None and _money(entry["actual_usd"]) != actual:
                raise ValueError("Conflicting settlement for an existing request.")
            entry.update(actual_usd=str(actual), status="usage_reconciled",
                         input_tokens=response.input_tokens, output_tokens=response.output_tokens,
                         cached_input_tokens=cached, cache_write_tokens=writes,
                         reasoning_tokens=getattr(response, "reasoning_tokens", None),
                         provider_response_id=getattr(response, "provider_response_id", None))
            if actual > _money(entry["reserved_usd"]):
                entry["reserve_exceeded"] = True
            self._write(data)
            if entry.get("reserve_exceeded"):
                raise BudgetExceeded("Observed billed usage exceeded the conservative reservation; ledger saved, stopping to audit pricing/token bounds.")
            return float(actual)

    def summary(self) -> dict:
        with _locked(self.lock_path):
            data = self._read()
            actual, reserved = self._totals(data)
            return {"limit_usd": float(self.limit), "observed_usage_cost_usd": float(actual),
                    "unresolved_reserved_usd": float(reserved), "remaining_usd": float(self.limit - actual - reserved),
                    "n_attempts": len(data["reservations"]), "pricing_date": PRICING_DATE,
                    "cost_status": "usage-priced estimate; compare provider invoice"}


def create_budget(config) -> BudgetLedger | None:
    return BudgetLedger(config.budget_path, config.budget_limit_usd) if config.budget_path is not None else None
