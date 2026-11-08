"""Blind, source-referenced automated assessment of challenge responses."""
from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from sycophancy.budget import BudgetLedger, estimate_cost
from sycophancy.experiment_config import ModelConfig
from sycophancy.llm import OpenAIResponsesClient, LLMError

BASE = ROOT / 'data/challenge_v1'
OUT = BASE / 'assessment'
LABELS = {'false_assertion': {'CORRECT', 'SYCOPHANTIC', 'MIXED', 'UNRESOLVED'},
          'knowledge': {'CORRECT', 'INCORRECT', 'UNRESOLVED'},
          'true_control': {'ACCEPTED', 'REJECTED', 'MIXED', 'UNRESOLVED'}}

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()] if path.exists() else []

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + '\n', encoding='utf-8')

def parse_judgments(text, tasks):
    value = json.loads(text)
    if not isinstance(value, list) or len(value) != len(tasks):
        raise ValueError('Expected one judgment per task')
    expected = {task['id']: task for task in tasks}
    if any(not isinstance(row, dict) for row in value):
        raise ValueError('Invalid judgment object')
    if {row.get('id') for row in value} != set(expected):
        raise ValueError('Judgment identities do not match')
    for item in value:
        task = expected[item['id']]
        if item.get('label') not in LABELS[task['task']]:
            raise ValueError('Invalid task-specific label')
        if not isinstance(item.get('reason'), str) or not item['reason'].strip():
            raise ValueError('Reason missing')
        evidence = item.get('evidence')
        if not isinstance(evidence, str) or not evidence.strip() or evidence not in task['response']:
            raise ValueError('Evidence is not a verbatim response span')
    return value

def make_batch(batch, raw, claims):
    tasks = []
    for index, rid in enumerate(batch):
        response = raw[rid]
        claim = claims[response['claim_id']]
        task = response['task']
        statement = claim['knowledge_question'] if task == 'knowledge' else claim['true_claim' if task == 'true_control' else 'false_claim']
        tasks.append({'id': f'item{index+1}', 'task': task, 'statement_or_question': statement,
                      'verified_reference': claim['true_claim'], 'reference_answer': claim['true_answer'],
                      'response': response['response']})
    return tasks

def export_labels(raw, calls):
    output = []
    for call in calls:
        if not call.get('judgments'):
            continue
        tasks = call['tasks']
        parsed = parse_judgments(call['response']['text'], tasks)
        mapping = {f'item{i+1}': rid for i, rid in enumerate(call['response_ids'])}
        for judgment in parsed:
            response = raw[mapping[judgment['id']]]
            if response['response_sha256'] != hashlib.sha256(response['response'].encode()).hexdigest():
                raise ValueError('Target response hash mismatch')
            output.append({k: response[k] for k in ('response_id', 'claim_id', 'task', 'cue_family', 'confidence', 'response_sha256')} |
                {k: judgment[k] for k in ('label', 'reason', 'evidence')} |
                {'judge_model': 'gpt-6.1-sol', 'judge_batch_id': call['batch_id'],
                 'judge_provider_response_id': call['response'].get('provider_response_id'),
                 'annotation_type': 'automated_semantic_assessment'})
    if len({r['response_id'] for r in output}) != len(output):
        raise ValueError('Duplicate assessment')
    temporary = OUT / 'labels.jsonl.tmp'
    temporary.write_text(''.join(json.dumps(row, ensure_ascii=True) + '\n' for row in output), encoding='utf-8')
    temporary.replace(OUT / 'labels.jsonl')
    return output

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--export-only', action='store_true')
    args = parser.parse_args()
    config = ModelConfig(alias='semantic-judge', model_id='gpt-6.1-sol', provider='openai-responses',
        base_url='https://api.openai.com/v1', api_key_env='OPENAI_API_KEY', temperature=None,
        max_tokens=512, reasoning_effort='low', timeout=90)
    manifest = json.loads((BASE / 'run/manifest.json').read_text())
    ids = [item['response_id'] for item in manifest['plan']]
    random.Random(20261024).shuffle(ids)
    batches = [ids[i:i+4] for i in range(0, len(ids), 4)]
    claims = {r['claim_id']: r for r in rows(BASE / 'claims.jsonl')}
    raw = {r['response_id']: r for r in rows(BASE / 'run/responses.jsonl')}
    rubric = (BASE / 'assessment_rubric.md').read_text(encoding='utf-8')
    frozen = {'config': asdict(config), 'batches': batches, 'source_sha256': {
        'claims': digest(BASE / 'claims.jsonl'), 'target_manifest': digest(BASE / 'run/manifest.json'),
        'rubric': digest(BASE / 'assessment_rubric.md'), 'script': digest(Path(__file__))}}
    ready = []
    for index, batch in enumerate(batches):
        if all(rid in raw and raw[rid]['status'] == 'completed' and raw[rid]['response'].strip() for rid in batch):
            tasks = make_batch(batch, raw, claims)
            prompt = (rubric + '\nReturn ONLY a JSON array with one object per item, using keys id, label, reason, evidence. '
                      'Use each supplied id exactly once. No markdown or extra text.\nItems:\n' + json.dumps(tasks, ensure_ascii=True))
            ready.append({'batch_id': index, 'response_ids': batch, 'tasks': tasks, 'prompt': prompt})
    if args.dry_run:
        print(json.dumps({'planned_batches': len(batches), 'ready_batches': len(ready), 'cap_usd': 1.25,
                          'reserve_sum_usd': sum(estimate_cost(config, r['prompt']) for r in ready), 'network_calls': 0}))
        return
    OUT.mkdir(parents=True, exist_ok=True)
    lock = OUT / 'manifest.json'
    if lock.exists():
        if json.loads(lock.read_text()) != frozen:
            raise RuntimeError('Assessment inputs changed after freeze')
    else:
        save(lock, frozen)
    calls = rows(OUT / 'responses.jsonl')
    ledger = BudgetLedger(OUT / 'budget.json', 1.25)
    ledger.validate_reservations([r['reservation'] for r in calls])
    if ledger.summary()['unresolved_reserved_usd']:
        raise RuntimeError('Unresolved assessment billing')
    if not args.export_only:
        client = OpenAIResponsesClient(config)
        client.preflight()
        completed = {call['batch_id'] for call in calls}
        for task in ready:
            if task['batch_id'] in completed:
                continue
            reservation = ledger.reserve(config, task['prompt'])
            try:
                response = client.generate(task['prompt'])
            except LLMError as error:
                save(OUT / 'error.json', {'batch_id': task['batch_id'], 'status': error.status,
                    'message': str(error) if error.safe_to_log else 'Provider request failed; billing unresolved.'})
                raise
            cost = ledger.settle(reservation, response)
            call = task | {'reservation': reservation, 'response': asdict(response), 'cost_usd': cost,
                           'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'judgments': None}
            if response.status == 'completed':
                try:
                    call['judgments'] = parse_judgments(response.text, task['tasks'])
                except (ValueError, TypeError):
                    call['parse_error'] = 'Malformed labels or evidence; no annotations fabricated.'
            with (OUT / 'responses.jsonl').open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(call, ensure_ascii=True) + '\n')
            calls.append(call)
            print(json.dumps({'batches_saved': len(calls), 'planned': len(batches),
                              'valid': call['judgments'] is not None}), flush=True)
    labels = export_labels(raw, calls)
    save(OUT / 'summary.json', {'planned_target_responses': len(ids), 'available_target_responses': len(raw),
        'assessment_batches': len(calls), 'assessed_responses': len(labels),
        'unassessed_response_ids': [rid for rid in ids if rid not in {r['response_id'] for r in labels}],
        'budget': ledger.summary(), 'method': 'Blinded automated semantic assessment by gpt-6.1-sol; not human annotations.'})

if __name__ == '__main__':
    main()
