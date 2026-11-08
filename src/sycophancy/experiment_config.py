"""Strict, secret-free experiment configuration (TOML, Python 3.11+)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import math
import os
from pathlib import Path
import re
import tomllib
from urllib.parse import urlsplit


def _integer(name: str, value: object, minimum: int) -> None:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}.")


def _number(name: str, value: object, minimum: float, maximum: float | None = None) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"{name} must be a finite number >= {minimum}.")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}.")


@dataclass(frozen=True)
class ModelConfig:
    alias: str
    model_id: str
    provider: str
    base_url: str
    api_key_env: str | None = None
    temperature: float | None = 0.0
    max_tokens: int = 192
    timeout: float = 120.0
    seed: int | None = None
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.alias, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", self.alias):
            raise ValueError("Model alias must be a short alphanumeric identifier.")
        if not isinstance(self.model_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/@+\-]*", self.model_id):
            raise ValueError("model_id must be an explicit nonblank provider model ID.")
        if self.provider not in {"openai-compatible", "llama_cpp", "openai-responses"}:
            raise ValueError(f"Unsupported provider {self.provider!r}.")
        if not isinstance(self.base_url, str):
            raise ValueError("base_url must be a URL.")
        url = urlsplit(self.base_url)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("base_url must have a host and no credentials, query, or fragment.")
        loopback = url.hostname in {"localhost", "127.0.0.1", "::1"}
        if url.scheme != "https" and not (url.scheme == "http" and loopback):
            raise ValueError("base_url must use HTTPS, except for an HTTP loopback local server.")
        if self.api_key_env is not None and (
            not isinstance(self.api_key_env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.api_key_env)
        ):
            raise ValueError("api_key_env must name an environment variable, never contain a key.")
        if not self.api_key_env and not (self.provider == "llama_cpp" and loopback):
            raise ValueError("A remote provider requires api_key_env.")
        if self.temperature is not None:
            _number("temperature", self.temperature, 0, 2)
        _integer("max_tokens", self.max_tokens, 1)
        _number("timeout", self.timeout, 0.001)
        if self.seed is not None:
            _integer("model seed", self.seed, 0)
        if self.reasoning_effort is not None and self.reasoning_effort not in {"none", "minimal", "low", "medium", "high", "xhigh"}:
            raise ValueError("reasoning_effort is not a recognized effort setting.")
        if self.provider == "openai-responses" and self.seed is not None:
            raise ValueError("Responses API does not support a generation seed; use experiment seed for shuffling.")
        if self.provider != "openai-responses" and self.reasoning_effort is not None:
            raise ValueError("reasoning_effort is currently implemented only for openai-responses.")


@dataclass(frozen=True)
class ExperimentConfig:
    dataset_path: Path
    run_dir: Path
    models: tuple[ModelConfig, ...]
    seed: int = 20261006
    max_requests: int = 2000
    retries: int = 2
    backoff_seconds: float = 1.0
    repetitions: int = 1
    require_verified: bool = False
    sample_claims: int | None = None
    budget_path: Path | None = None
    budget_limit_usd: float = 8.0
    prerequisite_run_dir: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "dataset_path", Path(self.dataset_path).resolve())
        object.__setattr__(self, "run_dir", Path(self.run_dir).resolve())
        object.__setattr__(self, "models", tuple(self.models))
        if self.budget_path is not None:
            object.__setattr__(self, "budget_path", Path(self.budget_path).resolve())
        if self.prerequisite_run_dir is not None:
            object.__setattr__(self, "prerequisite_run_dir", Path(self.prerequisite_run_dir).resolve())
            if self.prerequisite_run_dir == self.run_dir:
                raise ValueError("A run cannot name itself as its prerequisite.")
        _number("budget_limit_usd", self.budget_limit_usd, 0)
        if not self.models or any(not isinstance(model, ModelConfig) for model in self.models):
            raise ValueError("At least one valid ModelConfig is required.")
        aliases = [model.alias for model in self.models]
        if len(aliases) != len(set(aliases)):
            raise ValueError("Model aliases must be unique.")
        identities = [(model.provider, model.base_url, model.model_id) for model in self.models]
        if len(identities) != len(set(identities)):
            raise ValueError("Duplicate provider/base_url/model_id combinations are not separate models.")
        _integer("seed", self.seed, 0)
        _integer("max_requests", self.max_requests, 0)
        _integer("retries", self.retries, 0)
        _integer("repetitions", self.repetitions, 1)
        _number("backoff_seconds", self.backoff_seconds, 0)
        if type(self.require_verified) is not bool:
            raise ValueError("require_verified must be a boolean.")
        if self.sample_claims is not None:
            _integer("sample_claims", self.sample_claims, 1)

    def to_dict(self) -> dict:
        result = asdict(self)
        result["dataset_path"] = str(self.dataset_path)
        result["run_dir"] = str(self.run_dir)
        result["models"] = [asdict(model) for model in self.models]
        result["budget_path"] = str(self.budget_path) if self.budget_path is not None else None
        result["prerequisite_run_dir"] = str(self.prerequisite_run_dir) if self.prerequisite_run_dir is not None else None
        return result


def load_experiment_config(path: str | Path) -> ExperimentConfig:
    """Paths are relative to the TOML file, never the invoking working directory."""
    config_path = Path(path).resolve()
    with config_path.open("rb") as stream:
        values = tomllib.load(stream)
    known = {field.name for field in fields(ExperimentConfig)}
    unknown = set(values) - known
    if unknown:
        raise ValueError(f"Unknown experiment settings: {sorted(unknown)}")
    for key in ("dataset_path", "run_dir", "models"):
        if key not in values:
            raise ValueError(f"Missing required experiment setting: {key}")
    for key in ("dataset_path", "run_dir", "budget_path", "prerequisite_run_dir"):
        if key not in values:
            continue
        if not isinstance(values[key], str) or not values[key].strip():
            raise ValueError(f"{key} must be a nonblank path.")
        values[key] = config_path.parent / values[key]
    if not isinstance(values["models"], list):
        raise ValueError("models must be TOML [[models]] tables.")
    model_fields = {field.name for field in fields(ModelConfig)}
    models = []
    for value in values["models"]:
        if not isinstance(value, dict) or set(value) - model_fields:
            raise ValueError("Each model must contain only recognized model configuration fields.")
        try:
            if value.get("provider") == "openai-responses" and "temperature" not in value:
                value["temperature"] = None
            if value.get("provider") == "openai-responses":
                value["base_url"] = os.environ.get("OPENAI_BASE_URL", value.get("base_url", "https://api.openai.com/v1"))
            models.append(ModelConfig(**value))
        except TypeError as exc:
            raise ValueError("Each model needs alias, model_id, provider, and base_url.") from exc
    values["models"] = tuple(models)
    return ExperimentConfig(**values)
