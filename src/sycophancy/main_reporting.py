"""Main-study analysis of manifest-checked API records and explicit human labels."""
from __future__ import annotations

from collections import Counter
import csv
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .analysis import analyze_baseline
from .annotation import agreement_metrics, export_annotation, import_annotations
from .budget import usage_cost
from .cost_receipts import verify_frozen_cost_review
from .data import _atomic_text_file
from .diagnostics import load_ai_diagnostics, render_ai_diagnostics
from .evaluation import EVALUATOR_VERSION, evaluate_records
from . import evaluation
from .gee import analyze_gee
from .paths import resolve_recorded_path
from .reporting import error_patterns, load_run, write_json, write_table
from .runner import validate_budget_history


def load_metadata(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        rows=list(csv.DictReader(stream))
    result={}
    for row in rows:
        claim=row.get("claim_id")
        if not claim or claim in result or row.get("difficulty") not in {"easy","medium","hard"}:
            raise ValueError("Invalid or duplicated claim difficulty metadata.")
        if not row.get("subtopic") or not row.get("difficulty_reason"):
            raise ValueError("Difficulty metadata requires subtopic and rationale.")
        result[claim]=row
    return result


def _valid(row):
    return (row.get("status","success") in {"success","completed"}
            and isinstance(row.get("response"),str) and bool(row["response"].strip())
            and row.get("finish_reason") not in {"length","max_tokens","content_filter"})


def load_collection(run_dir, metadata_path):
    run_dir=Path(run_dir)
    collection=json.loads((run_dir/"collection_manifest.json").read_text(encoding="utf-8"))
    if collection.get("metadata_sha256") and hashlib.sha256(Path(metadata_path).read_bytes()).hexdigest()!=collection["metadata_sha256"]:
        raise ValueError("Difficulty metadata changed after collection was frozen.")
    if collection.get("evaluator_sha256") and hashlib.sha256(Path(evaluation.__file__).read_bytes()).hexdigest()!=collection["evaluator_sha256"]:
        raise ValueError("Evaluator code changed after main collection was frozen.")
    metadata=load_metadata(metadata_path)
    expected_models=[row["alias"] for row in collection["config"]["models"]]
    if len(expected_models)!=len(set(expected_models)):
        raise ValueError("Duplicated collection model.")
    records, runs, hashes, selections=[],[],set(),[]
    seen_models=set()
    for item in collection["model_runs"]:
        model=item["model"]
        if model in seen_models or model not in expected_models:
            raise ValueError("Unexpected or duplicated model run.")
        seen_models.add(model)
        manifest, rows, status=load_run(resolve_recorded_path(
            item["run_dir"], collection["config"].get("run_dir"), run_dir))
        spec=manifest["specification"]
        if spec!=item["specification"]:
            raise ValueError("Model run differs from the frozen collection specification.")
        if any(row["model"]!=model for row in rows):
            raise ValueError("Model identity mismatch.")
        hashes.add(spec["dataset_sha256"])
        selections.append(set(spec["selected_claim_ids"]))
        runs.append({"model":model,"run_id":manifest["run_id"],**status})
        records.extend(rows)
    if seen_models!=set(expected_models) or len(hashes)!=1 or any(s!=selections[0] for s in selections):
        raise ValueError("Models must share exactly the same selected dataset.")
    if set(metadata)!=selections[0]:
        raise ValueError("Difficulty metadata must cover exactly the selected claims.")
    if collection.get("aliases_path"):
        aliases_raw=resolve_recorded_path(collection["aliases_path"],
            collection["config"].get("run_dir"), run_dir).read_bytes()
        if hashlib.sha256(aliases_raw).hexdigest()!=collection.get("aliases_sha256"):
            raise ValueError("Answer aliases changed after main collection was frozen.")
        aliases=json.loads(aliases_raw)
        if set(aliases)!=set(metadata):
            raise ValueError("Answer aliases must cover exactly the selected claims.")
    ids=[row["response_id"] for row in records]
    if len(ids)!=len(set(ids)):
        raise ValueError("Duplicated response identity across model runs.")
    for row in records:
        row.update({key:metadata[row["claim_id"]][key] for key in ("difficulty","subtopic","difficulty_reason")})
    return collection, records, runs, metadata


def _table(headers, rows):
    def cell(value):
        return str(value).replace("|","\\|").replace("\n"," ")
    return "\n".join(["| "+" | ".join(headers)+" |", "| "+" | ".join("---" for _ in headers)+" |"]+
                     ["| "+" | ".join(cell(v) for v in row)+" |" for row in rows])


def _percent(value):
    return "unavailable" if value is None else f"{100*value:.2f}%"


def _pp(value):
    return "unavailable" if value is None else f"{100*value:+.2f} pp"


def subgroup_contrasts(analysis, field):
    grouped={}
    for row in analysis[f"rates_by_{field}"]:
        grouped.setdefault((row["model"],row[field]),{})[row["confidence"]]=row
    result=[]
    for (model,group),conditions in sorted(grouped.items()):
        if "low" not in conditions or "high" not in conditions:
            continue
        for outcome in ("sycophancy","correction"):
            result.append({"model":model,field:group,"outcome":outcome,
                           "high_minus_low":conditions["high"][outcome+"_rate"]-conditions["low"][outcome+"_rate"],
                           "n_low":conditions["low"]["n_responses"],"n_high":conditions["high"]["n_responses"],
                           "inference":"descriptive, not multiplicity-adjusted subgroup inference"})
    return result


def qualitative_examples(rows, patterns):
    index={}
    for row in rows:
        index.setdefault((row["model"],row["claim_id"],row.get("repetition",0)),{})[row["confidence"]]=row
    categories=("Confidence Flip","Always Correct","Reverse Flip","Always Sycophantic","Uncertain","Other mixed pattern")
    chosen=[]
    for category in categories:
        matches=sorted((p for p in patterns if p["pattern"]==category),key=lambda p:(p["model"],p["claim_id"],p["repetition"]))
        if not matches:
            chosen.append({"selection":category,"observed":False})
            continue
        p=matches[0]
        chosen.append({"selection":category,"observed":True,"model":p["model"],"claim_id":p["claim_id"],
                       "responses":index[(p["model"],p["claim_id"],p["repetition"])]})
    by_claim={}
    for row in rows:
        by_claim.setdefault((row["claim_id"],row["confidence"],row.get("repetition",0)),[]).append(row)
    differing=[(key,value) for key,value in sorted(by_claim.items()) if len({r["label"] for r in value})>1]
    chosen.append({"selection":"Different models", "observed":bool(differing),
                   "responses":differing[0][1] if differing else []})
    for domain in sorted({row["domain"] for row in rows}):
        failures=sorted((row for row in rows if row["domain"]==domain and row["label"]!="CORRECT"),
                        key=lambda r:(r["model"],r["claim_id"],r["confidence"]))
        chosen.append({"selection":f"Automatic non-CORRECT example: {domain}","observed":bool(failures),
                       "responses":failures[:1]})
    return chosen


def _validate_robustness_manifest(collection, manifest, metadata):
    """Require the actual design described by the fixed robustness report."""
    spec=manifest["specification"]
    settings=spec["config"]
    main_spec=collection["model_runs"][0]["specification"]
    selected=spec.get("selected_claim_ids",[])
    models=settings.get("models",[])
    if (spec.get("dataset_sha256")!=main_spec["dataset_sha256"]
            or len(selected)!=50 or len(set(selected))!=50 or not set(selected)<=set(metadata)
            or settings.get("sample_claims")!=50 or settings.get("repetitions")!=3
            or len(models)!=1 or models[0].get("model_id")!="gpt-6-luna"):
        raise ValueError("Robustness manifest must use the main dataset, 50 selected claims, and three Luna repetitions.")
    model=models[0]
    main_models=[row for row in collection["config"]["models"] if row["model_id"]=="gpt-6-luna"]
    if (len(main_models)!=1 or model.get("provider")!=main_models[0].get("provider")
            or model.get("base_url")!=main_models[0].get("base_url")
            or model.get("reasoning_effort")!="low" or model.get("max_tokens")!=512
            or model.get("temperature") is not None or model.get("seed") is not None):
        raise ValueError("Robustness generation settings differ from the required Luna design.")
    for key in ("reasoning_effort","max_tokens","temperature","seed"):
        if model.get(key)!=main_models[0].get(key):
            raise ValueError("Robustness generation settings differ from the main Luna model.")
    expected={(claim,condition,repetition) for claim in selected
              for condition in ("low","neutral","high") for repetition in (1,2,3)}
    plan=manifest.get("plan",[])
    actual={(row.get("claim_id"),row.get("confidence"),row.get("repetition")) for row in plan}
    if len(plan)!=450 or actual!=expected or spec.get("total_responses")!=450:
        raise ValueError("Robustness plan does not contain all 450 required request units.")
    for row in plan:
        if (row.get("model")!=model["alias"] or row.get("model_id")!="gpt-6-luna"
                or row.get("provider")!=model["provider"] or row.get("reasoning_effort")!="low"
                or row.get("max_output_tokens")!=512 or row.get("temperature") is not None
                or row.get("generation_seed") is not None):
            raise ValueError("Robustness plan contains mismatched model or generation metadata.")


def analyze_main(run_dir, metadata_path, output_dir, *, n_bootstrap=5000, seed=20261006,
                 annotation_path=None, robustness_dir=None, make_plots=True):
    run_dir,output_dir=Path(run_dir),Path(output_dir)
    frozen_cost_review=verify_frozen_cost_review(run_dir)
    collection,records,runs,metadata=load_collection(run_dir,metadata_path)
    valid=[row for row in records if _valid(row)]
    if not valid:
        raise ValueError("No complete real responses; no empirical main report generated.")
    budget_config=collection["config"]
    budget_path=resolve_recorded_path(budget_config["budget_path"],budget_config.get("run_dir"),run_dir)
    budget=validate_budget_history(run_dir,budget_path,budget_config["budget_limit_usd"],relocate_paths=True)
    if budget is None:
        raise ValueError("Main analysis requires its original global budget ledger.")
    robust_input=None
    if robustness_dir and (Path(robustness_dir)/"manifest.json").exists():
        robust_input=load_run(robustness_dir)
        _validate_robustness_manifest(collection,robust_input[0],metadata)
        validate_budget_history(robustness_dir,budget_path,budget_config["budget_limit_usd"],relocate_paths=True)
    aliases=json.loads(resolve_recorded_path(collection["aliases_path"],
        budget_config.get("run_dir"),run_dir).read_text(encoding="utf-8")) if collection.get("aliases_path") else {}
    rows=evaluate_records(valid,aliases)
    diagnostics=load_ai_diagnostics(output_dir/"evaluator_diagnostics.json",rows,collection)
    analysis=analyze_baseline(rows,n_bootstrap=n_bootstrap,seed=seed)
    sensitivity=analyze_baseline(rows,n_bootstrap=n_bootstrap,seed=seed,include_review=False)
    gee=analyze_gee(rows)
    patterns=error_patterns(rows)
    examples=qualitative_examples(rows,patterns)
    annotation_path=Path(annotation_path) if annotation_path else run_dir/"annotation.csv"
    if not annotation_path.exists():
        export_annotation(rows,annotation_path,size=min(225,len(rows)),seed=seed)
    human_rows=import_annotations(annotation_path,rows)
    human=agreement_metrics(human_rows)
    known_cost=sum((usage_cost(row["model_id"],row["input_tokens"],row["output_tokens"],
                              row.get("cached_input_tokens") or 0,row.get("cache_write_tokens") or 0)
                    for row in records if type(row.get("input_tokens")) is int and type(row.get("output_tokens")) is int),Decimal(0))
    planned=sum(run["planned_responses"] for run in runs)
    complete=all(run["status"]=="complete" for run in runs) and len(valid)==planned
    run_id="collection-"+hashlib.sha256("|".join(sorted(run["run_id"] for run in runs)).encode()).hexdigest()[:24]
    usage={field:{"observed_subtotal":sum(row[field] for row in records if row.get(field) is not None)
                    if any(row.get(field) is not None for row in records) else None,
                  "records_missing_usage":sum(row.get(field) is None for row in records)}
           for field in ("input_tokens","output_tokens","reasoning_tokens","cached_input_tokens","cache_write_tokens")}
    summary={"run_id":run_id,"status":"complete" if complete else "incomplete","planned_responses":planned,
             "completed_responses":len(valid),"persisted_responses":len(records),"runs":runs,
             "usage":usage,"observed_response_cost_usd":float(known_cost),"global_budget":budget,
             "evaluator_version":EVALUATOR_VERSION,"metadata_sha256":hashlib.sha256(Path(metadata_path).read_bytes()).hexdigest()}
    model_usage=[]
    for model in config_models(collection):
        model_rows=[row for row in records if row["model"]==model]
        known=[row for row in model_rows if type(row.get("input_tokens")) is int and type(row.get("output_tokens")) is int]
        latencies=[row["latency"] for row in model_rows if row.get("latency") is not None]
        item={"model":model,"n_responses":len(model_rows),"priced_responses":len(known),
              "observed_cost_usd":float(sum((usage_cost(row["model_id"],row["input_tokens"],row["output_tokens"],
                    row.get("cached_input_tokens") or 0,row.get("cache_write_tokens") or 0) for row in known),Decimal(0))) if known else None,
              "mean_latency_seconds":sum(latencies)/len(latencies) if latencies else None}
        for field in ("input_tokens","output_tokens","reasoning_tokens"):
            observed=[row[field] for row in model_rows if row.get(field) is not None]
            item[field]=sum(observed) if observed else None
            item[field+"_missing"]=len(model_rows)-len(observed)
        model_usage.append(item)
    summary["model_usage"]=model_usage
    robust=None
    if robust_input is not None:
        robust_manifest,robust_records,robust_collection=robust_input
        robust_valid=[dict(row,**{key:metadata[row["claim_id"]][key] for key in ("difficulty","subtopic","difficulty_reason")})
                      for row in robust_records if _valid(row)]
        if robust_valid:
            robust_rows=evaluate_records(robust_valid,aliases)
            targeted=[row for row in robust_rows if row['label']!='CORRECT']
            targeted_path=Path(robustness_dir)/'annotation_non_correct.csv'
            targeted_ready=robust_collection['status']=='complete' and len(robust_rows)==450
            if targeted_ready and targeted and not targeted_path.exists():
                export_annotation(targeted,targeted_path,size=len(targeted),seed=seed+1)
            selected=set(robust_manifest['specification']['selected_claim_ids'])
            main_matched=[row for row in rows if row['claim_id'] in selected and row['model_id']=='gpt-6-luna']
            robust_cost=sum((usage_cost(row['model_id'],row['input_tokens'],row['output_tokens'],
                                       row.get('cached_input_tokens') or 0,row.get('cache_write_tokens') or 0)
                             for row in robust_records if type(row.get('input_tokens')) is int and type(row.get('output_tokens')) is int),Decimal(0))
            robust={"collection":robust_collection,"analysis":analyze_baseline(robust_rows,n_bootstrap=n_bootstrap,seed=seed+1),
                    "main_matched_subset":analyze_baseline(main_matched,n_bootstrap=n_bootstrap,seed=seed+1),
                    "observed_response_cost_usd":float(robust_cost),
                    "usage":{field:sum(row.get(field) or 0 for row in robust_records)
                             if all(row.get(field) is not None for row in robust_records) else None
                             for field in ('input_tokens','output_tokens','reasoning_tokens')},
                    "repetition_effects":repetition_effects(robust_rows)}
            robust['targeted_review_count']=len(targeted) if targeted_ready else None
            robust['sycophantic_claim_ids']=sorted({row['claim_id'] for row in robust_rows if row['label']=='SYCOPHANTIC'})
            write_table(Path(robustness_dir)/"evaluated_responses.csv",robust_rows)
            write_table(output_dir/"tables"/"robustness_repetition_effects.csv",robust['repetition_effects'])
    for name,value in (("main_analysis",analysis),("main_sensitivity_review_excluded",sensitivity),
                       ("main_gee",gee),("main_human_validation",human),("main_collection",summary),
                       ("main_qualitative_examples",examples),("robustness_analysis",robust)):
        write_json(output_dir/f"{name}.json",value)
    write_table(run_dir/"evaluated_responses.csv",rows)
    write_table(output_dir/"tables"/"model_usage.csv",model_usage)
    for name in ("rates_by_confidence","rates_by_domain","rates_by_difficulty","cochran_q","mcnemar"):
        write_table(output_dir/"tables"/f"main_{name}.csv",analysis[name])
    for name in ("rates","contrasts"):
        write_table(output_dir/"tables"/f"main_bootstrap_{name}.csv",analysis["bootstrap"][name])
    write_table(output_dir/"tables"/"error_analysis.csv",patterns)
    for field in ("domain","difficulty"):
        write_table(output_dir/"tables"/f"main_{field}_effects.csv",subgroup_contrasts(analysis,field))
    coefficients=[dict(row,fit=name) for name,fit in [("combined",gee["combined"]),
                  *((fit["model"],fit) for fit in gee["per_model"])]
                  for row in fit.get("coefficients",[])]
    write_table(output_dir/"tables"/"main_gee_coefficients.csv",coefficients)
    if make_plots:
        from .plots import make_figures
        make_figures(analysis,gee,human,output_dir/"figures")
    write_main_report(collection,metadata,summary,analysis,sensitivity,gee,human,patterns,examples,robust,output_dir/"main_results.md",diagnostics=diagnostics)
    # Aggregate stage gate for the subsequent repetition robustness collection.
    write_json(run_dir/"run_summary.json",summary)
    if frozen_cost_review:
        verify_frozen_cost_review(run_dir)
    elif complete and budget["review_ready"] and all(usage[k]["records_missing_usage"]==0 for k in ("input_tokens","output_tokens")):
        write_json(run_dir/"cost_review.json",{"run_id":run_id,"status":"reviewed",
                   "review_method":"automated_usage_and_completeness_check",
                   "observed_usage_cost_usd":float(known_cost),"expected_evaluable_responses":len(rows),
                   "global_budget_snapshot":budget,"note":"Observed usage priced at frozen tariffs, not an account invoice."})
    elif (run_dir/"cost_review.json").exists():
        write_json(run_dir/"cost_review.json",{"run_id":run_id,"status":"pending",
                   "reason":"Collection completeness, known usage, and reconciled budget evidence are required."})
    return {"status":summary["status"],"n_evaluable":len(rows),"human_labels":human["n"],
            "cost_usd":float(known_cost),"report":str(output_dir/"main_results.md")}


def config_models(collection):
    return [model["alias"] for model in collection["config"]["models"]]


def repetition_effects(rows):
    """Descriptive repeat-level effects; inference still clusters by claim."""
    result=[]
    for repetition in sorted({row['repetition'] for row in rows}):
        group=[row for row in rows if row['repetition']==repetition]
        for outcome,label in (('correction','CORRECT'),('sycophancy','SYCOPHANTIC')):
            cells={condition:[row for row in group if row['confidence']==condition] for condition in ('low','high')}
            rates={condition:sum(row['label']==label for row in cell)/len(cell) if cell else None for condition,cell in cells.items()}
            result.append({'repetition':repetition,'outcome':outcome,'n_low':len(cells['low']),'n_high':len(cells['high']),
                           'high_minus_low':rates['high']-rates['low'] if all(v is not None for v in rates.values()) else None})
    return result


def write_main_report(collection,metadata,summary,analysis,sensitivity,gee,human,patterns,examples,robust,path,*,diagnostics=None):
    config=collection["config"]
    companions=[f"[{title}]({name})" for name,title in (
        ("ai_review_results.md","expanded AI semantic review"),
        ("supplemental_analysis.md","post-hoc supplemental analysis"))
        if (Path(path).parent/name).is_file()]
    history=(["**Review history:** The diagnostic excerpt below concerns the initial non-CORRECT-only audit. "
              "Later companion reports: "+", ".join(companions)+
              ". They preserve primary labels and do not provide human validation.",""] if companions else [])
    lines=["# Main experiment results","",*history,"## 1. Research Question","",
           "Does expressed user confidence affect an LLM's willingness to challenge objectively incorrect information? H0: no confidence effect on explicit false-fact acceptance. Directional H1: greater expressed confidence increases acceptance; reduced correction is a separate secondary endpoint.","",
           "## 2. Dataset","",f"{len(metadata)} source-reviewed claims across five domains. Difficulty counts: {dict(Counter(r['difficulty'] for r in metadata.values()))}. Difficulty is a prospective rubric-based judgment, not a measured model-knowledge score. Full sources and evidence are in data/verification/main_sources.jsonl; independent human fact review has not been performed.","",
           "The initial 50-claim pilot had perfect automatic correction. The main corpus expanded topical coverage after that pilot; this is not preregistration before observing the pilot.","",
           "## 3. Models","",", ".join(f"`{m['model_id']}`" for m in config['models'])+". These are capability tiers within one provider/family, not independent model families.","",
           "## 4. Experimental Design","","Identical LOW/NEUTRAL/HIGH templates, reasoning.effort=low and max_output_tokens=512. Temperature/top_p/generation seed omitted; no tools, retrieval or shared conversation. The same seeded shuffled request order was used for each model (order seed 20261006). Parallel scheduling does not modify prompts or per-model order. Provider aliases may change over time; raw provider model IDs and timestamps are retained.","",
           f"Collection: **{summary['status']}**; planned {summary['planned_responses']}, persisted {summary['persisted_responses']}, evaluable {summary['completed_responses']}. Observed response usage-priced cost: **${summary['observed_response_cost_usd']:.7f}**. Global observed cost ${summary['global_budget']['observed_usage_cost_usd']:.7f}; unresolved reserved ${summary['global_budget']['unresolved_reserved_usd']:.7f}. These are tariff calculations, not provider invoices. Reasoning tokens are included in output tokens.","",
           "Token accounting: `"+json.dumps(summary['usage'])+"`.","",
           _table(["Model","Responses priced / persisted","Input tokens","Output tokens","Reasoning tokens (included)","Observed cost USD"],
                  [[r['model'],f"{r['priced_responses']}/{r['n_responses']}",r['input_tokens'],r['output_tokens'],r['reasoning_tokens'],r['observed_cost_usd']] for r in summary['model_usage']]),
           "","## 5. Evaluation","",
           f"Heuristic evaluator {EVALUATOR_VERSION}; three provisional labels. Review flags: {analysis['metadata']['needs_human_review']}/{summary['completed_responses']}. UNCERTAIN includes linguistic matching failures until adjudicated; it must not automatically be interpreted as the model expressing uncertainty. Baseline-developed aliases were frozen before main collection.","",
           f"Stratified human-review CSV: data/runs/main/annotation.csv. Human labels supplied: {human['n']}; status: {human['status']}. Accuracy, macro F1 and confusion counts are unavailable when no human labels exist. A stratified audit sample is not an unbiased estimate of natural class prevalence.","",
           *render_ai_diagnostics(diagnostics),
           "## 6. Main Results","",
           _table(["Model","Condition","N","Correction","Sycophancy","Uncertainty"],
                  [[r['model'],r['confidence'],r['n_responses'],_percent(r['correction_rate']),_percent(r['sycophancy_rate']),_percent(r['uncertainty_rate'])] for r in analysis['rates_by_confidence']]),"",
           _table(["Model","Outcome","Contrast","Effect","95% cluster CI","Status"],
                  [[r['model'],r['outcome'],r['contrast'],_pp(r['estimate']),f"{_pp(r['ci_lower'])} to {_pp(r['ci_upper'])}",r['status']] for r in analysis['bootstrap']['contrasts']]),"",
           "Figures (PNG; matching PDFs are in the same folder): [Sycophancy](figures/01_sycophancy_by_confidence.png), [Correction](figures/02_correction_by_confidence.png), [HIGH−LOW](figures/03_high_low_effect.png), [Domain](figures/04_domain_by_confidence.png), [Heatmap](figures/05_model_confidence_heatmap.png), [Odds ratios](figures/06_odds_ratio_forest.png), [Human confusion matrix](figures/07_human_confusion_matrix.png). Unavailable panels explicitly explain missing evidence.","",
           "## 7. Statistical Analysis","","Complete triplets only. Claim-cluster bootstrap preserves models, conditions and repetitions within claim; intervals are pointwise percentile intervals. Degenerate empirical intervals do not establish equivalence. Exact McNemar tests use Holm adjustment within model/outcome families; Cochran Q is undefined with no discordance. Full paired tests are saved in reports/tables/main_*.csv.","",
           f"Primary GEE (binomial logit, claim clusters, robust covariance): **{gee['combined']['status']}**. {gee['combined'].get('reason','')} Formula: `{gee['combined'].get('formula','')}`. Coefficients, odds ratios, 95% CIs and robust joint tests are preserved in main_gee.json. No finite odds ratio is fabricated for separation or constant outcomes.","",
           f"Paired coverage: {json.dumps(analysis['paired'])}. Review-excluded sensitivity complete blocks: {sensitivity['paired']['n_complete_blocks']}; exclusions can strongly select easier response forms and are not a replacement for human validation.","",
           _table(['Model','Outcome','Cochran Q','Asymptotic p','Discordant claims','Status'],
                  [[r['model'],r['outcome'],r['statistic'],r['p_value'],r['n_discordant'],r['status']] for r in analysis['cochran_q'] if r['outcome']!='uncertainty']),"",
           _table(['Model','Outcome','HIGH−LOW exact McNemar p','Holm p'],
                  [[r['model'],r['outcome'],r['p_value'],r['p_holm']] for r in analysis['mcnemar'] if r['contrast']=='high - low' and r['outcome']!='uncertainty']),"",
           "Few discordant claims make the asymptotic Q approximation fragile. A pointwise percentile bootstrap interval can exclude zero while a discrete exact McNemar test and multiplicity-adjusted test do not reject; these procedures have different finite-sample properties. Neither resolves evaluator errors.","",
           "## 8. Domain Analysis","",
           _table(["Model","Domain","Outcome","HIGH−LOW","N low/high"],[[r['model'],r['domain'],r['outcome'],_pp(r['high_minus_low']),f"{r['n_low']}/{r['n_high']}"] for r in subgroup_contrasts(analysis,'domain')]),"",
           "Difficulty breakdowns and descriptive contrasts are saved alongside domain tables. They cannot identify whether an individual model knew a fact; no independent knowledge-only control was collected.","",
           "## 9. Robustness",""]
    if robust:
        lines += [f"Collection status: {robust['collection']['status']}; evaluable records: {robust['analysis']['metadata']['n_selected_responses']}. Fifty seeded random claims, three repetitions on gpt-6-luna, same reasoning.effort=low and omitted sampling settings. This tests repeatability under provider nondeterminism, not a temperature intervention. Repetitions are clustered jointly by claim.","",
                  f"Observed robustness response cost: ${robust['observed_response_cost_usd']:.7f}; token usage: {json.dumps(robust['usage'])}. Reasoning tokens are already included in output tokens.","",
                  (f"An additional targeted sheet, data/runs/robustness/annotation_non_correct.csv, contains {robust['targeted_review_count']} non-CORRECT responses for human adjudication. It excludes automatically CORRECT responses and cannot estimate population accuracy; it is separate from the 225-item main validation sample."
                   if robust['targeted_review_count'] else "A targeted non-CORRECT human-review sheet will be available if the complete robustness collection contains such responses."),"",
                  _table(["Model","Outcome","Contrast","Effect","95% CI"],[[r['model'],r['outcome'],r['contrast'],_pp(r['estimate']),f"{_pp(r['ci_lower'])} to {_pp(r['ci_upper'])}"] for r in robust['analysis']['bootstrap']['contrasts']]),""]
        lines += ['Comparison on the same 50 claims from the original main Luna collection (avoids changing claim composition):','',
                  _table(['Outcome','Main matched HIGH−LOW','95% cluster CI'],[[r['outcome'],_pp(r['estimate']),f"{_pp(r['ci_lower'])} to {_pp(r['ci_upper'])}"] for r in robust['main_matched_subset']['bootstrap']['contrasts'] if r['contrast']=='high - low']),
                  '',_table(['Repetition','Outcome','HIGH−LOW','N low/high'],[[r['repetition'],r['outcome'],_pp(r['high_minus_low']),f"{r['n_low']}/{r['n_high']}"] for r in robust['repetition_effects']]),'',
                  'Repeat-level differences are descriptive, not independent replications of claim sampling. Repetition-level exact paired tests and joint claim bootstrap are retained in robustness_analysis.json. Automatic-label limitations also apply here.','']
        if (Path(path).parent/'robustness_diagnostics.md').exists():
            lines += ['A separate [post-hoc AI diagnostic review of robustness](robustness_diagnostics.md) inspects non-CORRECT cases, including any mixed endorsement and repair. It is not human validation and does not replace these primary labels or estimates.','']
    else:
        lines += ["Not collected yet. No robustness result is inferred or fabricated.",""]
    lines += ["## 10. Error Analysis","",str(dict(Counter(row['pattern'] for row in patterns))),"","Complete model/claim/repetition patterns are in reports/tables/error_analysis.csv.","","## 11. Qualitative Examples","","Deterministic selection: first lexicographic observed claim/model per pattern, first label disagreement across models, and first non-CORRECT response per domain. Selection uses provisional labels, not a claim that the excerpts were human-adjudicated.",""]
    for example in examples:
        lines += [f"**{example['selection']}**",""]
        if not example['observed']:
            lines += ["No observed case under the automatic labels.",""]
            continue
        selected=example['responses']
        selected=selected.values() if isinstance(selected,dict) else selected
        for row in selected:
            lines += [f"- {row['claim_id']} / {row['model']} / {row['confidence']} ({row['label']}): {json.dumps(row['response'],ensure_ascii=False)}"]
        lines += [""]
    lines += ["## 12. Limitations","","Automatic labels lack human validation unless supplied above. Hand-curated facts, proxy difficulty, residual cue length/wording differences, one model family, ceiling effects and absent independent knowledge controls limit generalization. Confidence ordering was not validated by independent human ratings. Zero observed sycophancy and non-significant tests do not demonstrate absence or equivalence. Main analysis is exploratory after a pilot. Human annotations are never generated by an LLM and presented as human work.","","## 13. Main Findings",""]
    for row in analysis['bootstrap']['contrasts']:
        if row['outcome']=='sycophancy' and row['contrast']=='high - low':
            lines += [f"- {row['model']}: observed HIGH−LOW acceptance difference {_pp(row['estimate'])}, 95% empirical cluster CI {_pp(row['ci_lower'])} to {_pp(row['ci_upper'])} ({row['status']}). This is an automatic-label estimate."]
    if diagnostics:
        lines += ['', 'The diagnostic AI audit found apparent missed factual repairs and mixed endorsement/repair cases. Therefore provisional correction differences are not established behavioral effects, and zero SYCOPHANTIC labels do not certify that all responses challenged the premise cleanly. Human adjudication remains necessary.']
    contrast=next((r for r in robust['analysis']['bootstrap']['contrasts'] if r['outcome']=='sycophancy' and r['contrast']=='high - low'),None) if robust else None
    if contrast:
        lines += ['',f"Repeatability check: automatic SYCOPHANTIC HIGH−LOW {_pp(contrast['estimate'])}, 95% claim-cluster CI {_pp(contrast['ci_lower'])} to {_pp(contrast['ci_upper'])}. Positive automatic labels occur in {len(robust['sycophantic_claim_ids'])} distinct claims: {', '.join(robust['sycophantic_claim_ids']) or 'none'}. Repeated outputs on one claim do not increase the number of independent claim clusters. Inspect the targeted human sheet and diagnostic review before interpreting this as factual acceptance or a general confidence effect."]
    with _atomic_text_file(Path(path)) as stream:
        stream.write("\n".join(lines)+"\n")
