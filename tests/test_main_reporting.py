import csv
from dataclasses import replace
import json
import hashlib
from pathlib import Path
import shutil

import pytest

from sycophancy.experiment_config import ExperimentConfig, ModelConfig
from sycophancy.llm import BaseLLMClient, LLMResponse
from sycophancy.main_reporting import analyze_main, load_collection, load_metadata, _validate_robustness_manifest, repetition_effects
from sycophancy.multi_model import run_multi_model
from sycophancy.runner import _validate_prerequisite, build_plan, run_experiment


class TestOnlyClient(BaseLLMClient):
    __test__=False
    def generate(self,prompt,*,seed=None):
        return LLMResponse("Incorrect; this is a test-only answer.",input_tokens=20,output_tokens=10,
                           cached_input_tokens=0,cache_write_tokens=0,reasoning_tokens=0)


@pytest.fixture
def collected(tmp_path):
    names=("gpt-6-luna","gpt-6.1-sol","gpt-6-astra")
    models=tuple(ModelConfig(alias=name,model_id=name,provider="openai-responses",
                            base_url="https://api.openai.com/v1",api_key_env="OPENAI_API_KEY",
                            temperature=None,reasoning_effort="low",max_tokens=512) for name in names)
    config=ExperimentConfig(dataset_path=Path(__file__).parents[1]/"data/raw/claims_baseline.csv",
                            run_dir=tmp_path/"main",models=models,max_requests=100,sample_claims=2,
                            budget_path=tmp_path/"budget.json",budget_limit_usd=8)
    run_multi_model(config,client_factory=lambda _:TestOnlyClient())
    manifest=json.loads((config.run_dir/"collection_manifest.json").read_text())
    ids=manifest["model_runs"][0]["specification"]["selected_claim_ids"]
    metadata=tmp_path/"metadata.csv"
    with metadata.open("w",newline="",encoding="utf-8") as stream:
        writer=csv.writer(stream)
        writer.writerow(["claim_id","difficulty","subtopic","difficulty_reason"])
        writer.writerows((claim,"easy","test subtopic","test-only rubric") for claim in ids)
    return config,metadata,tmp_path/"reports"


def test_full_report_and_cost_gate_without_fabricated_human_labels(collected):
    config,metadata,reports=collected
    before={p:p.read_bytes() for p in config.run_dir.glob("*/responses.jsonl")}
    result=analyze_main(config.run_dir,metadata,reports,n_bootstrap=10,make_plots=False)
    assert result["status"]=="complete"
    assert result["n_evaluable"]==18
    assert result["human_labels"]==0
    human=json.loads((reports/"main_human_validation.json").read_text())
    assert human["accuracy"] is None and human["macro_f1"] is None
    assert (reports/"main_results.md").exists()
    assert (reports/"tables/error_analysis.csv").exists()
    summary=json.loads((reports/"main_collection.json").read_text())
    assert len(summary["model_usage"])==3
    assert all(row["priced_responses"]==6 and row["input_tokens"]==120 for row in summary["model_usage"])
    assert sum(row["observed_cost_usd"] for row in summary["model_usage"])==pytest.approx(result["cost_usd"])
    assert all(p.read_bytes()==raw for p,raw in before.items())
    _validate_prerequisite(replace(config,run_dir=config.run_dir.parent/"robustness",
                                   prerequisite_run_dir=config.run_dir))
    again=analyze_main(config.run_dir,metadata,reports,n_bootstrap=10,make_plots=False)
    assert again["cost_usd"]==result["cost_usd"]


@pytest.mark.parametrize("receipt_state", ["intact", "missing", "tampered"])
def test_frozen_main_gate_keeps_historical_ledger_snapshot(collected, receipt_state):
    config, metadata, reports = collected
    analyze_main(config.run_dir, metadata, reports, n_bootstrap=10, make_plots=False)
    receipt = config.run_dir / "cost_review.json"
    historical = receipt.read_bytes()
    assert json.loads(historical)["global_budget_snapshot"]["historical_reservations_checked"] == 18
    root = config.run_dir.parent
    authority = root / "data/validation_v2/coordinator_manifest.json"
    authority.parent.mkdir(parents=True)
    authority.write_text(json.dumps({"source_sha256": {
        receipt.relative_to(root).as_posix(): hashlib.sha256(historical).hexdigest()}}))
    later = replace(config, run_dir=root / "later-stage", models=(config.models[0],), sample_claims=1)
    run_experiment(later, client_factory=lambda _: TestOnlyClient())
    copy = root / "relocated-frozen"
    for path in (config.run_dir, later.run_dir, root / "data"):
        shutil.copytree(path, copy / path.name)
    for path in (config.budget_path, metadata):
        shutil.copy2(path, copy / path.name)
    copied_receipt = copy / config.run_dir.name / "cost_review.json"
    if receipt_state == "missing":
        copied_receipt.unlink()
    elif receipt_state == "tampered":
        copied_receipt.write_bytes(historical + b"\n")
    copied_reports = copy / "reports"
    if receipt_state != "intact":
        with pytest.raises(ValueError, match="Frozen historical cost review"):
            analyze_main(copied_receipt.parent, copy / metadata.name, copied_reports,
                         n_bootstrap=10, make_plots=False)
        assert not copied_reports.exists()
    else:
        analyze_main(copied_receipt.parent, copy / metadata.name, copied_reports,
                     n_bootstrap=10, make_plots=False)
        assert copied_receipt.read_bytes() == historical
        fresh = json.loads((copied_reports / "main_collection.json").read_text())
        assert fresh["global_budget"]["n_attempts"] == 21
        assert fresh["global_budget"]["historical_reservations_checked"] == 18
        assert fresh["global_budget"]["observed_usage_cost_usd"] > json.loads(historical)["global_budget_snapshot"]["observed_usage_cost_usd"]
    assert receipt.read_bytes() == historical


def test_metadata_must_cover_all_selected_claims(collected):
    config,metadata,_=collected
    lines=metadata.read_text().splitlines()
    metadata.write_text("\n".join(lines[:-1])+"\n")
    with pytest.raises(ValueError,match="exactly"):
        load_collection(config.run_dir,metadata)


@pytest.fixture
def relocated_collection(collected):
    config, metadata, _ = collected
    source = config.run_dir.parent
    predecessor = replace(config, run_dir=source/"baseline", models=(config.models[0],), sample_claims=1)
    run_experiment(predecessor, client_factory=lambda _: TestOnlyClient())
    manifest_path = config.run_dir/"collection_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    aliases = source/"aliases.json"
    aliases.write_text(json.dumps({claim: {} for claim in load_metadata(metadata)}))
    manifest.update(aliases_path=str(aliases), aliases_sha256=hashlib.sha256(aliases.read_bytes()).hexdigest())
    manifest["config"]["prerequisite_run_dir"] = str(predecessor.run_dir)
    manifest_path.write_text(json.dumps(manifest))
    copy = source/"relocated"
    copy.mkdir()
    for name in ("main", "baseline"):
        shutil.copytree(source/name, copy/name)
    for path in (metadata, aliases, config.budget_path):
        shutil.copy2(path, copy/path.name)
    return source, copy


def test_relocated_main_uses_copied_responses_even_when_original_exists(relocated_collection):
    source, copy = relocated_collection
    frozen = {p: p.read_bytes() for p in copy.rglob("*manifest.json")}
    path = next((copy/"main").glob("*/responses.jsonl"))
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[0]["response"] = "A correction found only in the relocated copy."
    path.write_text("".join(json.dumps(row)+"\n" for row in rows))
    _, loaded, _, _ = load_collection(copy/"main", copy/"metadata.csv")
    assert rows[0]["response"] in {row["response"] for row in loaded}
    result = analyze_main(copy/"main", copy/"metadata.csv", copy/"reports", n_bootstrap=10, make_plots=False)
    assert result["n_evaluable"] == 18
    assert json.loads((copy/"reports/main_collection.json").read_text())["global_budget"]["historical_reservations_checked"] == 21
    assert all(path.read_bytes() == content for path, content in frozen.items())
    assert not (source/"main/evaluated_responses.csv").exists()


@pytest.mark.parametrize("failure", ["aliases", "model", "ledger", "predecessor", "missing_predecessor"])
def test_relocated_main_never_falls_back_to_healthy_original(relocated_collection, failure):
    source, copy = relocated_collection
    if failure == "aliases":
        (copy/"aliases.json").write_text("{}")
        expected = "Answer aliases changed"
    elif failure == "model":
        next((copy/"main").glob("*/manifest.json")).unlink()
        expected = "manifest.json"
    elif failure == "missing_predecessor":
        for name in ("manifest.json", "run_summary.json"):
            (copy/"baseline"/name).unlink()
        expected = "predecessor evidence missing"
    else:
        folder = copy/"baseline" if failure == "predecessor" else next((copy/"main").glob("gpt-*"))
        receipt = json.loads((folder/"responses.jsonl").read_text().splitlines()[0])["budget_reservation_id"]
        ledger = json.loads((copy/"budget.json").read_text())
        del ledger["reservations"][receipt]
        (copy/"budget.json").write_text(json.dumps(ledger))
        expected = "historical request reservation"
    with pytest.raises((ValueError, FileNotFoundError), match=expected):
        analyze_main(copy/"main", copy/"metadata.csv", copy/"reports", n_bootstrap=10, make_plots=False)
    assert (source/"budget.json").exists()
    assert not (copy/"main/cost_review.json").exists()


def test_metadata_duplicate_rejected(tmp_path):
    metadata=tmp_path/"metadata.csv"
    metadata.write_text("claim_id,difficulty,subtopic,difficulty_reason\na,easy,test,test\na,easy,test,test\n")
    with pytest.raises(ValueError,match="duplicated"):
        load_metadata(metadata)


def test_collection_manifest_model_mismatch_rejected(collected):
    config,metadata,_=collected
    path=config.run_dir/"collection_manifest.json"
    value=json.loads(path.read_text())
    value["model_runs"][1]["model"]=value["model_runs"][0]["model"]
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError,match="duplicated"):
        load_collection(config.run_dir,metadata)


def test_empty_response_collection_cannot_create_empirical_report(collected):
    config,metadata,reports=collected
    for path in config.run_dir.glob("*/responses.jsonl"):
        path.write_text("")
    with pytest.raises(ValueError,match="No complete real responses"):
        analyze_main(config.run_dir,metadata,reports,n_bootstrap=10,make_plots=False)
    assert not (reports/"main_results.md").exists()


def test_incomplete_collection_does_not_pass_robustness_gate(collected):
    config,metadata,reports=collected
    path=next(config.run_dir.glob("*/responses.jsonl"))
    path.write_text("\n".join(path.read_text().splitlines()[:-1])+"\n")
    result=analyze_main(config.run_dir,metadata,reports,n_bootstrap=10,make_plots=False)
    assert result["status"]=="incomplete"
    assert not (config.run_dir/"cost_review.json").exists()


@pytest.mark.parametrize("failure",["deleted_ledger","absent_receipt","response_pointer","attempt_receipt"])
def test_main_cost_review_requires_original_budget_evidence(collected,failure):
    config,metadata,reports=collected
    if failure=="deleted_ledger":
        config.budget_path.unlink()
    elif failure=="absent_receipt":
        data=json.loads(config.budget_path.read_text())
        del data["reservations"][next(iter(data["reservations"]))]
        config.budget_path.write_text(json.dumps(data))
    else:
        path=next(config.run_dir.glob("*/responses.jsonl" if failure=="response_pointer" else "*/attempts.jsonl"))
        rows=[json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["budget_reservation_id"]="missing-test-only-receipt"
        path.write_text("".join(json.dumps(row)+"\n" for row in rows))
    with pytest.raises(ValueError,match="[Bb]udget|reservation"):
        analyze_main(config.run_dir,metadata,reports,n_bootstrap=10,make_plots=False)
    assert not (config.run_dir/"cost_review.json").exists()


@pytest.mark.parametrize("failure",["unknown_billing","overrun","zero_unknown_reservation"])
def test_unreconciled_cost_invalidates_prior_main_review(collected,failure):
    config,metadata,reports=collected
    analyze_main(config.run_dir,metadata,reports,n_bootstrap=10,make_plots=False)
    data=json.loads(config.budget_path.read_text())
    entry=next(iter(data["reservations"].values()))
    if failure=="overrun":
        entry["reserve_exceeded"]=True
    else:
        entry["actual_usd"]=None
        if failure=="zero_unknown_reservation":
            entry["reserved_usd"]="0"
    config.budget_path.write_text(json.dumps(data))
    result=analyze_main(config.run_dir,metadata,reports,n_bootstrap=10,make_plots=False)
    assert result["status"]=="complete"  # Response collection remains complete.
    assert json.loads((config.run_dir/"cost_review.json").read_text())["status"]=="pending"
    with pytest.raises(ValueError,match="cost review"):
        _validate_prerequisite(replace(config,run_dir=config.run_dir.parent/"robustness",prerequisite_run_dir=config.run_dir))


def test_main_audits_baseline_predecessor_receipts(collected):
    config,metadata,reports=collected
    predecessor=replace(config,run_dir=config.run_dir.parent/"baseline",models=(config.models[0],),sample_claims=1)
    run_experiment(predecessor,client_factory=lambda _:TestOnlyClient())
    path=config.run_dir/"collection_manifest.json"
    collection=json.loads(path.read_text())
    collection["config"]["prerequisite_run_dir"]=str(predecessor.run_dir)
    path.write_text(json.dumps(collection))
    receipt=json.loads((predecessor.run_dir/"responses.jsonl").read_text().splitlines()[0])["budget_reservation_id"]
    data=json.loads(config.budget_path.read_text())
    del data["reservations"][receipt]
    config.budget_path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match="historical request reservation"):
        analyze_main(config.run_dir,metadata,reports,n_bootstrap=10,make_plots=False)


def test_parallel_main_audits_actual_predecessor_before_workers(collected,monkeypatch):
    config,_,_=collected
    predecessor=replace(config,run_dir=config.run_dir.parent/"baseline",models=(config.models[0],))
    summary=run_experiment(predecessor,client_factory=lambda _:TestOnlyClient())
    (predecessor.run_dir/"cost_review.json").write_text(json.dumps({
        "run_id":summary["run_id"],"status":"reviewed","observed_usage_cost_usd":0.01,
        "expected_evaluable_responses":summary["completed_responses"]}))
    next_config=replace(config,run_dir=config.run_dir.parent/"main-after-baseline",prerequisite_run_dir=predecessor.run_dir)
    # multi_model holds its directly imported real validator. Workers must use
    # its completed audit instead of touching the OS ledger lock concurrently.
    monkeypatch.setattr("sycophancy.runner._validate_prerequisite",
                        lambda _:pytest.fail("worker repeated the coordinator's budget audit"))
    result=run_multi_model(next_config,client_factory=lambda _:TestOnlyClient())
    assert result["status"]=="complete" and result["completed_responses"]==18


def test_baseline_like_run_cannot_be_attached_as_robustness(collected):
    config,metadata,reports=collected
    with pytest.raises(ValueError,match="Robustness manifest"):
        analyze_main(config.run_dir,metadata,reports,n_bootstrap=10,make_plots=False,
                     robustness_dir=config.run_dir/config.models[0].alias)


@pytest.fixture
def robustness_design(collected):
    config,_,_=collected
    main_config=replace(config,sample_claims=None)
    main_spec,_=build_plan(main_config)
    robust_config=replace(main_config,models=(config.models[0],),sample_claims=50,repetitions=3,
                          run_dir=config.run_dir.parent/"robustness")
    spec,plan=build_plan(robust_config)
    collection={"config":main_config.to_dict(),"model_runs":[{"specification":main_spec}]}
    return collection,{"specification":spec,"plan":plan},{claim:{} for claim in main_spec["selected_claim_ids"]}


def test_expected_robustness_design_is_accepted(robustness_design):
    _validate_robustness_manifest(*robustness_design)


@pytest.mark.parametrize("change",["dataset","repetitions","model","reasoning","max_tokens","temperature","seed","plan_seed","missing_condition"])
def test_wrong_robustness_design_rejected(robustness_design,change):
    collection,manifest,metadata=robustness_design
    spec=manifest["specification"]
    if change=="dataset":
        spec["dataset_sha256"]="different-test-dataset"
    elif change=="repetitions":
        spec["config"]["repetitions"]=1
    elif change=="missing_condition":
        manifest["plan"].pop()
    elif change=="plan_seed":
        manifest["plan"][0]["generation_seed"]=5
    else:
        key={"model":"model_id","reasoning":"reasoning_effort"}.get(change,change)
        value={"model":"gpt-6-astra","reasoning":"high","max_tokens":1024,"temperature":0.1,"seed":12}[change]
        spec["config"]["models"][0][key]=value
    with pytest.raises(ValueError,match="Robustness"):
        _validate_robustness_manifest(collection,manifest,metadata)


def test_repetition_effects_keep_opposing_repeats_separate():
    rows=[{'repetition':rep,'confidence':condition,'label':label}
          for rep,low,high in [(1,'CORRECT','UNCERTAIN'),(2,'UNCERTAIN','CORRECT')]
          for condition,label in [('low',low),('high',high)]]
    result=repetition_effects(rows)
    correction=[row for row in result if row['outcome']=='correction']
    assert [row['high_minus_low'] for row in correction]==[-1,1]
    assert all(row['n_low']==row['n_high']==1 for row in result)
    assert all(row['high_minus_low']==0 for row in result if row['outcome']=='sycophancy')


def test_repetition_effects_do_not_impute_a_missing_condition():
    result=repetition_effects([{'repetition':1,'confidence':'low','label':'CORRECT'}])
    assert all(row['high_minus_low'] is None and row['n_high']==0 for row in result)
