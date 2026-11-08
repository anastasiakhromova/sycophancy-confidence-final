from dataclasses import replace
from pathlib import Path

import pytest

from sycophancy.experiment_config import ExperimentConfig, ModelConfig, load_experiment_config


def valid_model(**changes):
    values = dict(alias="baseline", model_id="explicit-test-model", provider="openai-compatible",
                  base_url="https://example.test/v1", api_key_env="TEST_MODEL_KEY")
    values.update(changes)
    return ModelConfig(**values)


@pytest.mark.parametrize("changes", [
    {"alias": "bad alias"}, {"model_id": ""}, {"provider": "madeup"},
    {"base_url": "http://example.test/v1"}, {"base_url": "https://key:secret@example.test/v1"},
    {"base_url": "https://example.test/v1?key=secret"}, {"base_url": "https://example.test/#secret"},
    {"api_key_env": None}, {"api_key_env": "sk-this-is-a-secret"}, {"temperature": True},
    {"temperature": -1}, {"temperature": 2.1}, {"temperature": float("nan")},
    {"max_tokens": 0}, {"max_tokens": True}, {"timeout": 0}, {"seed": -1},
])
def test_reject_invalid_model_config(changes):
    with pytest.raises(ValueError):
        valid_model(**changes)


def test_local_loopback_does_not_require_key():
    assert valid_model(provider="llama_cpp", base_url="http://127.0.0.1:8080/v1", api_key_env=None)


@pytest.mark.parametrize("changes", [
    {"seed": True}, {"max_requests": -1}, {"retries": 0.2}, {"repetitions": 0},
    {"sample_claims": 0}, {"backoff_seconds": float("inf")}, {"require_verified": "false"},
    {"models": ()},
])
def test_reject_invalid_experiment_config(tmp_path, changes):
    values = dict(dataset_path=tmp_path / "claims.csv", run_dir=tmp_path / "run", models=(valid_model(),))
    values.update(changes)
    with pytest.raises(ValueError):
        ExperimentConfig(**values)


def test_duplicate_alias_or_actual_model_fails(tmp_path):
    model = valid_model()
    for second in (model, replace(model, alias="another")):
        with pytest.raises(ValueError):
            ExperimentConfig(tmp_path / "claims.csv", tmp_path / "run", (model, second))


def test_toml_paths_relative_to_config_and_unknown_fields_fail(tmp_path):
    path = tmp_path / "config.toml"
    content = '''dataset_path = "data/claims.csv"
run_dir = "runs/test"
[[models]]
alias = "test"
model_id = "model"
provider = "llama_cpp"
base_url = "http://127.0.0.1:8080/v1"
'''
    path.write_text(content, encoding="utf-8")
    config = load_experiment_config(path)
    assert config.dataset_path == tmp_path / "data" / "claims.csv"
    assert config.run_dir == tmp_path / "runs" / "test"
    assert "api_key" not in config.to_dict()
    path.write_text("typo = 1\n" + content, encoding="utf-8")
    with pytest.raises(ValueError, match="Unknown experiment"):
        load_experiment_config(path)
    path.write_text(content + 'api_key = "secret"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="recognized"):
        load_experiment_config(path)
