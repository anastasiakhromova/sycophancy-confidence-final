import io
import json
from urllib.error import HTTPError, URLError

import pytest

from sycophancy.experiment_config import ModelConfig
from sycophancy.llm import LLMError, OpenAICompatibleClient, OpenAIResponsesClient


def config():
    return ModelConfig("test", "actual-model", "openai-compatible", "https://example.test/v1", "TEST_MODEL_KEY")


def client(monkeypatch):
    monkeypatch.setenv("TEST_MODEL_KEY", "secret-only-in-memory")
    return OpenAICompatibleClient(config())


def test_missing_key_fails_without_network(monkeypatch):
    monkeypatch.delenv("TEST_MODEL_KEY", raising=False)
    with pytest.raises(LLMError, match="Missing API key environment variable: TEST_MODEL_KEY"):
        OpenAICompatibleClient(config())


def test_http_shape_independent_conversation_and_usage(monkeypatch):
    instance = client(monkeypatch)
    requests = []

    def open_request(request, timeout):
        requests.append(request)
        assert timeout == 120
        return io.BytesIO(json.dumps({"model": "actual-model", "system_fingerprint": "fp_test",
            "choices": [{"message": {"content": "A real-shaped test fixture"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 15, "completion_tokens": 8}}).encode())

    monkeypatch.setattr(instance._opener, "open", open_request)
    first = instance.generate("prompt one", seed=9)
    second = instance.generate("prompt two", seed=10)
    assert first.input_tokens == 15 and second.output_tokens == 8
    assert first.provider_model == "actual-model" and first.system_fingerprint == "fp_test"
    assert first.latency >= 0
    assert requests[0].full_url == "https://example.test/v1/chat/completions"
    for index, request in enumerate(requests):
        body = json.loads(request.data)
        assert len(body["messages"]) == 1
        assert body["messages"][0]["role"] == "user"
        assert body["seed"] == 9 + index
        assert body["temperature"] == 0
        assert body["stream"] is False
        assert request.get_header("Authorization") == "Bearer secret-only-in-memory"


@pytest.mark.parametrize("status,retryable", [(400, False), (401, False), (429, True), (503, True), (302, False)])
def test_http_errors_sanitized(monkeypatch, status, retryable):
    instance = client(monkeypatch)

    def fail(*args, **kwargs):
        raise HTTPError("https://example.test/v1", status, "SECRET", {}, io.BytesIO(b"SECRET"))

    monkeypatch.setattr(instance._opener, "open", fail)
    with pytest.raises(LLMError) as failure:
        instance.generate("prompt")
    assert failure.value.retryable is retryable
    assert failure.value.status == status
    assert "SECRET" not in str(failure.value)


@pytest.mark.parametrize("payload", [b"not-json", b"{}", b'{"choices":[]}',
    b'{"choices":[{"message":{"content":""}}]}',
    b'{"choices":[{"message":{"content":"x"}}],"usage":{"prompt_tokens":-1}}'])
def test_invalid_response_never_becomes_success(monkeypatch, payload):
    instance = client(monkeypatch)
    monkeypatch.setattr(instance._opener, "open", lambda *a, **kw: io.BytesIO(payload))
    with pytest.raises(LLMError):
        instance.generate("prompt")


def test_network_error_sanitized(monkeypatch):
    instance = client(monkeypatch)
    def fail(*args, **kwargs):
        raise URLError("SECRET host credential")
    monkeypatch.setattr(instance._opener, "open", fail)
    with pytest.raises(LLMError, match="connection or timeout") as failure:
        instance.generate("prompt")
    assert failure.value.retryable
    assert "SECRET" not in str(failure.value)


def responses_client(monkeypatch):
    monkeypatch.setenv("TEST_MODEL_KEY", "sk-test-super-secret")
    return OpenAIResponsesClient(ModelConfig("luna", "gpt-6-luna", "openai-responses",
        "https://api.openai.com/v1", "TEST_MODEL_KEY", temperature=None,
        max_tokens=512, reasoning_effort="low"))


def test_responses_request_has_exact_user_selected_controls(monkeypatch):
    instance = responses_client(monkeypatch)
    requests = []
    def open_request(request, timeout):
        requests.append(request)
        if request.get_method() == "GET":
            return io.BytesIO(b'{"id":"gpt-6-luna"}')
        return io.BytesIO(json.dumps({"id":"resp_test", "model":"gpt-6-luna", "status":"completed", "service_tier":"default",
            "output":[{"type":"reasoning","summary":[{"text":"not assistant output"}]},
                      {"type":"message","role":"assistant","content":[{"type":"output_text","text":"Answer."}]}],
            "usage":{"input_tokens":30,"output_tokens":40,"input_tokens_details":{"cached_tokens":10},
                     "output_tokens_details":{"reasoning_tokens":20}}}).encode())
    monkeypatch.setattr(instance._opener,"open",open_request)
    instance.preflight()
    response = instance.generate("prompt")
    assert requests[0].full_url == "https://api.openai.com/v1/models/gpt-6-luna"
    assert requests[1].full_url == "https://api.openai.com/v1/responses"
    body=json.loads(requests[1].data)
    assert body["reasoning"]=={"effort":"low"} and body["max_output_tokens"]==512
    assert body["tools"]==[] and body["store"] is False and body["service_tier"]=="default"
    assert not {"temperature","top_p","seed","previous_response_id"} & body.keys()
    assert response.text=="Answer." and response.provider_response_id=="resp_test"
    assert response.input_tokens==30 and response.output_tokens==40 and response.reasoning_tokens==20
    assert response.cached_input_tokens==10


def test_responses_incomplete_empty_preserves_billed_usage(monkeypatch):
    instance = responses_client(monkeypatch)
    payload={"id":"resp_incomplete", "model":"gpt-6-luna", "status":"incomplete", "output":[],
             "incomplete_details":{"reason":"max_output_tokens"}, "usage":{"input_tokens":20,"output_tokens":512,
             "output_tokens_details":{"reasoning_tokens":512}}}
    monkeypatch.setattr(instance._opener,"open",lambda *a,**kw:io.BytesIO(json.dumps(payload).encode()))
    response=instance.generate("prompt")
    assert response.status=="incomplete" and response.text==""
    assert response.output_tokens==512 and response.incomplete_reason=="max_output_tokens"


def test_responses_error_retains_api_message_but_redacts_keys(monkeypatch):
    instance = responses_client(monkeypatch)
    def fail(*args,**kwargs):
        payload=json.dumps({"error":{"code":"model_not_found","message":"Unavailable model; sk-test-super-secret Bearer abcdef"}}).encode()
        raise HTTPError("https://api.openai.com/v1/responses",404,"x",{},io.BytesIO(payload))
    monkeypatch.setattr(instance._opener,"open",fail)
    with pytest.raises(LLMError) as failure:
        instance.generate("prompt")
    assert failure.value.status==404 and not failure.value.retryable and failure.value.safe_to_log
    assert "model_not_found" in str(failure.value) and "Unavailable model" in str(failure.value)
    assert "super-secret" not in str(failure.value) and "abcdef" not in str(failure.value)


def test_responses_never_sends_generation_seed(monkeypatch):
    instance=responses_client(monkeypatch)
    with pytest.raises(LLMError,match="generation seed"):
        instance.generate("prompt",seed=1)
