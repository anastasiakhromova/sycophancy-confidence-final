"""Real HTTP inference clients; no synthetic-response fallback exists.

API shape: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
Responses API: https://developers.openai.com/api/reference/resources/responses/methods/create
Local server: https://github.com/ggml-org/llama.cpp/tree/master/tools/server
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import json
import os
import re
import time
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from .experiment_config import ModelConfig


class LLMError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False, status: int | None = None, safe_to_log: bool = False):
        super().__init__(message)
        self.retryable = retryable
        self.status = status
        self.safe_to_log = safe_to_log


@dataclass(frozen=True)
class LLMResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency: float | None = None
    provider_model: str | None = None
    finish_reason: str | None = None
    system_fingerprint: str | None = None
    cached_input_tokens: int | None = None
    cache_write_tokens: int | None = None
    reasoning_tokens: int | None = None
    provider_response_id: str | None = None
    service_tier: str | None = None
    status: str = "completed"
    incomplete_reason: str | None = None


class BaseLLMClient(ABC):
    def preflight(self) -> None:
        """Optionally check availability without generating or charging model tokens."""

    @abstractmethod
    def generate(self, prompt: str, *, seed: int | None = None) -> LLMResponse:
        """Send one independent user message with no shared conversation state."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward Authorization to another endpoint.


class OpenAICompatibleClient(BaseLLMClient):
    def __init__(self, config: ModelConfig):
        self.config = config
        self._api_key = os.environ.get(config.api_key_env, "") if config.api_key_env else ""
        if config.api_key_env and not self._api_key.strip():
            raise LLMError(f"Missing API key environment variable: {config.api_key_env}")
        self._opener = build_opener(_NoRedirect())

    def generate(self, prompt: str, *, seed: int | None = None) -> LLMResponse:
        body = {
            "model": self.config.model_id,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "stream": False,
        }
        effective_seed = self.config.seed if seed is None else seed
        if effective_seed is not None:
            body["seed"] = effective_seed
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = Request(
            self.config.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers=headers, method="POST",
        )
        started = time.perf_counter()
        try:
            with self._opener.open(request, timeout=self.config.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            # Provider bodies may contain secrets or echoed prompts. Never log them.
            raise LLMError(f"Provider HTTP error {exc.code}", status=exc.code,
                           retryable=exc.code in {408, 409, 425, 429} or exc.code >= 500) from None
        except (URLError, TimeoutError, ConnectionError, OSError):
            raise LLMError("Provider connection or timeout failure", retryable=True) from None
        except (UnicodeError, json.JSONDecodeError):
            raise LLMError("Provider returned malformed JSON", retryable=True) from None
        try:
            choice = result["choices"][0]
            message = choice["message"]
            text = message.get("content") or message.get("refusal")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("empty content")
            usage = result.get("usage") or {}
            tokens = [usage.get("prompt_tokens"), usage.get("completion_tokens")]
            if any(value is not None and (type(value) is not int or value < 0) for value in tokens):
                raise ValueError("invalid usage")
            metadata = [result.get("model"), choice.get("finish_reason"), result.get("system_fingerprint")]
            if any(value is not None and not isinstance(value, str) for value in metadata):
                raise ValueError("invalid provider metadata")
            return LLMResponse(
                text=text, input_tokens=tokens[0], output_tokens=tokens[1],
                latency=time.perf_counter() - started,
                provider_model=result.get("model"), finish_reason=choice.get("finish_reason"),
                system_fingerprint=result.get("system_fingerprint"),
            )
        except (TypeError, KeyError, IndexError, ValueError, AttributeError):
            raise LLMError("Provider response has no valid assistant text or usage", retryable=True) from None


def create_client(config: ModelConfig) -> BaseLLMClient:
    """Select the explicitly configured real HTTP API; never substitute a model."""
    if config.provider == "openai-responses":
        return OpenAIResponsesClient(config)
    return OpenAICompatibleClient(config)


class OpenAIResponsesClient(BaseLLMClient):
    """Responses API with no tools, no persisted API state, and no sampling overrides."""

    def __init__(self, config: ModelConfig):
        self.config = config
        self._api_key = os.environ.get(config.api_key_env, "") if config.api_key_env else ""
        if not self._api_key.strip():
            raise LLMError(f"Missing API key environment variable: {config.api_key_env}")
        if config.temperature is not None:
            raise LLMError("openai-responses experiments require temperature to be omitted (None).")
        self._opener = build_opener(_NoRedirect())

    def _safe_error(self, raw: bytes) -> str:
        try:
            error = json.loads(raw.decode("utf-8")).get("error", {})
            text = str(error.get("message", "Provider returned an unspecified API error"))
            if error.get("code"):
                text = f"{error['code']}: {text}"
        except (UnicodeError, ValueError, AttributeError):
            text = "Provider returned a non-JSON API error"
        text = text.replace(self._api_key, "[REDACTED]")
        text = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", text)
        text = re.sub(r"\bsk-[A-Za-z0-9_\-]+", "[REDACTED]", text)
        return text[:1500]

    def _request(self, endpoint: str, body: dict | None = None) -> dict:
        request = Request(
            self.config.base_url.rstrip("/") + endpoint,
            data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8") if body is not None else None,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json", "Accept": "application/json"},
            method="POST" if body is not None else "GET",
        )
        try:
            with self._opener.open(request, timeout=self.config.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise ValueError("Expected JSON object")
                return result
        except HTTPError as exc:
            message = self._safe_error(exc.read(16384))
            raise LLMError(f"Provider HTTP {exc.code}: {message}", status=exc.code,
                           retryable=exc.code in {408, 409, 425, 429} or exc.code >= 500, safe_to_log=True) from None
        except (URLError, TimeoutError, ConnectionError, OSError):
            raise LLMError("Provider connection or timeout failure", retryable=True) from None
        except (UnicodeError, ValueError):
            raise LLMError("Provider returned malformed JSON", retryable=True) from None

    def preflight(self) -> None:
        result = self._request("/models/" + quote(self.config.model_id, safe=""))
        if result.get("id") != self.config.model_id:
            raise LLMError("Model availability response did not match the requested explicit model ID.")

    def generate(self, prompt: str, *, seed: int | None = None) -> LLMResponse:
        if seed is not None:
            raise LLMError("Responses API does not support generation seed.")
        body = {"model": self.config.model_id, "input": [{"role": "user", "content": prompt}],
                "max_output_tokens": self.config.max_tokens, "store": False, "tools": [], "service_tier": "default"}
        if self.config.reasoning_effort is not None:
            body["reasoning"] = {"effort": self.config.reasoning_effort}
        started = time.perf_counter()
        result = self._request("/responses", body)
        try:
            parts = []
            for item in result.get("output", []):
                if item.get("type") == "message" and item.get("role") == "assistant":
                    for content in item.get("content", []):
                        if content.get("type") == "output_text":
                            parts.append(content["text"])
                        elif content.get("type") == "refusal":
                            parts.append(content["refusal"])
            if any(not isinstance(part, str) for part in parts):
                raise ValueError("Nontext assistant message")
            text = "\n".join(parts)
            status = result.get("status", "completed")
            if status not in {"completed", "incomplete", "failed", "cancelled"}:
                raise ValueError("Unrecognized synchronous response status")
            if not text.strip() and status != "incomplete":
                raise ValueError("No assistant text")
            usage = result.get("usage") or {}
            input_details = usage.get("input_tokens_details") or {}
            output_details = usage.get("output_tokens_details") or {}
            tokens = [usage.get("input_tokens"), usage.get("output_tokens"), input_details.get("cached_tokens"),
                      input_details.get("cache_write_tokens", input_details.get("cache_creation_tokens")),
                      output_details.get("reasoning_tokens")]
            if any(value is not None and (type(value) is not int or value < 0) for value in tokens):
                raise ValueError("Invalid usage")
            metadata = [result.get("model"), result.get("id"), result.get("service_tier"),
                        (result.get("incomplete_details") or {}).get("reason")]
            if any(value is not None and not isinstance(value, str) for value in metadata):
                raise ValueError("Invalid response metadata")
            return LLMResponse(text=text, input_tokens=tokens[0], output_tokens=tokens[1],
                cached_input_tokens=tokens[2], cache_write_tokens=tokens[3], reasoning_tokens=tokens[4],
                latency=time.perf_counter() - started, provider_model=result.get("model"),
                provider_response_id=result.get("id"), service_tier=result.get("service_tier"), status=status,
                finish_reason=status, incomplete_reason=(result.get("incomplete_details") or {}).get("reason"))
        except (KeyError, TypeError, AttributeError, ValueError):
            raise LLMError("Responses API returned invalid assistant output or usage; billing may have occurred") from None
