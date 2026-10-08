"""Frozen, offline sentence-pair diagnostic; never writes product judgments."""
import argparse
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/knowledge/evaluations/business_support_mechanism_20261008'
OUT = ROOT / 'data/knowledge/evaluations/business_nli_20261009'
MODEL = 'bekalebendong/xlm-roberta-large-text-entailment-88'
REVISION = '9c0c0ab36e1eebf0912ad0af23201528fa9d44c1'
LABELS = ['entailment', 'neutral', 'contradiction']


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def freeze():
    assert not (OUT / 'freeze.json').exists(), 'Frozen inputs already exist'
    original = BASE.parent / 'business_condition_scope_20261008/request_direct_narrow.json'
    stopped = BASE / 'r02_followup/stopped_run.json'
    packet = json.loads(read(original)['messages'][1]['content'])
    claims = deepcopy(packet['claims'])
    parent = read(stopped)
    mapping = parent['units'][6]['reference_map']
    original_id = next(key for key, value in mapping.items() if value == 'c11')
    c11 = next(c for c in parent['claims'] if c['id'] == original_id)
    assert c11['raw'] == dict(Head='양수인 미방문 시 구비서류', Relation='포함한다',
                              Tail='양수인 신분증 사본(법인의 경우 법인인감증명서)')
    claims.append(dict(id='c11', raw=deepcopy(c11['raw']), original_claim_id=original_id))
    # Preserve every delivered source block and its order, including list parents.
    premise = '\n'.join(b['text'] for b in packet['blocks'])
    assert all(b['text'] in premise for b in packet['blocks'])
    assert {p for row in packet['source_parents'] for p in row['parent_block_ids']} <= {
        b['id'] for b in packet['blocks']}
    inputs = [dict(id=c['id'], premise=premise,
        hypothesis=c['raw'].get('Event') or ' — '.join(c['raw'][k] for k in ('Head', 'Relation', 'Tail')),
        raw_candidate=c['raw']) for c in claims]
    write(OUT / 'inputs.json', inputs)
    write(OUT / 'source_packet.json', packet)
    criteria = dict(expected={'c13': 'entailment', 'c46': 'entailment', 'c47': 'neutral', 'c11': 'entailment'},
        basis=dict(c13='Parent missing-buyer condition and transfer document are preserved.',
                   c46='Missing-buyer condition and proxy documents are preserved.',
                   c47='Regional-number return-then-change does not entail return for every plate change; no converse exemption/prohibition is stated.',
                   c11='An includes relation for one actual listed document is true without enumerating the entire required document list.'),
        previous_product_gold=dict(c47='incorrect scope expansion; not a claim of explicit logical contradiction'),
        gate='All four exact labels required. Core normal damage, c47 entailment, or c47 contradiction fails. No tuning or retry.',
        limits='Label discrimination only; no error field, reason, correction, approval or requirement-completion success.',
        exposure='All four development exposed. Museum H01-H08/A01/A02 already exposed; no confirmed unused evaluation set.',
        unused_followup='Create and freeze a small independent set only if development gate passes.',
        not_model_input=True)
    write(OUT / 'criteria.json', criteria)
    write(OUT / 'freeze.json', dict(model=MODEL, revision=REVISION, labels=LABELS,
        label_authority=f'https://huggingface.co/{MODEL}/blob/{REVISION}/README.md',
        device='cpu', dtype='float32', truncation=False, training_length=192,
        single_pass=True, model_comparison='Mechanism plus model and serialization differ from prior generative baseline.',
        serialization='Original delivered block texts joined in original order; Event unchanged; relation claims use existing Head — Relation — Tail representation.',
        source_files={str(p.relative_to(ROOT)): sha(p) for p in [original, stopped]},
        files={p.name: sha(p) for p in [OUT/'inputs.json', OUT/'criteria.json', OUT/'source_packet.json']},
        script_sha256=sha(Path(__file__)), versions={n: importlib.metadata.version(n) for n in
            ['torch', 'transformers', 'safetensors', 'tokenizers', 'huggingface-hub']}))


def run():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    frozen = read(OUT / 'freeze.json')
    assert sha(Path(__file__)) == frozen['script_sha256']
    assert all(sha(OUT/name) == value for name, value in frozen['files'].items())
    assert all(sha(ROOT/name) == value for name, value in frozen['source_files'].items())
    assert not (OUT / 'run_started.json').exists(), 'Single frozen execution only'
    folder = Path(read(OUT / 'download.json')['path'])
    assert folder.name == REVISION
    files = {p.name: sha(p) for p in folder.iterdir() if p.is_file()}
    write(OUT/'checkpoint_hashes.json', dict(model=MODEL, revision=REVISION, files=files))
    tokenizer = AutoTokenizer.from_pretrained(folder, use_fast=True, local_files_only=True, trust_remote_code=False)
    config = read(folder / 'config.json')
    assert config['id2label'] == {str(i): f'LABEL_{i}' for i in range(3)}
    pairs = read(OUT / 'inputs.json')
    encoded = [tokenizer(p['premise'], p['hypothesis'], truncation=False, return_tensors='pt') for p in pairs]
    maximum = min(tokenizer.model_max_length, config['max_position_embeddings'] - config['pad_token_id'] - 1)
    preflight = [dict(id=p['id'], token_count=e['input_ids'].shape[1],
        above_training_length=e['input_ids'].shape[1] > 192,
        within_architecture=e['input_ids'].shape[1] <= maximum,
        input_ids=e['input_ids'][0].tolist()) for p, e in zip(pairs, encoded)]
    write(OUT / 'length_preflight.json', dict(training_length=192, architecture_positions=config['max_position_embeddings'],
        tokenizer_max_length=tokenizer.model_max_length, effective_pair_maximum=maximum, truncation=False, cases=preflight))
    write(OUT/'run_started.json', dict(freeze_sha256=sha(OUT/'freeze.json'), checkpoint_sha256=sha(OUT/'checkpoint_hashes.json')))
    load_started = time.monotonic()
    model = AutoModelForSequenceClassification.from_pretrained(folder, local_files_only=True,
        trust_remote_code=False, use_safetensors=True, torch_dtype=torch.float32).to('cpu').eval()
    result = dict(model=MODEL, revision=REVISION, device='cpu', dtype='float32', labels=LABELS,
                  load_s=time.monotonic()-load_started, model_calls=0, cases=[])
    for pair, inputs, scope in zip(pairs, encoded, preflight):
        record = dict(scope)
        if not scope['within_architecture']:
            record.update(status='input_capacity', logits=None, softmax=None, predicted=None)
        else:
            started = time.monotonic()
            with torch.inference_mode():
                logits = model(**inputs).logits[0]
            record.update(status='succeeded', elapsed_s=time.monotonic()-started,
                logits=logits.tolist(), softmax=torch.softmax(logits, dim=-1).tolist(),
                argmax=int(logits.argmax()), predicted=LABELS[int(logits.argmax())])
            result['model_calls'] += 1
        result['cases'].append(record)
        write(OUT/'result.json', result)
        print(pair['id'], record['status'], record['predicted'], flush=True)
    criteria = read(OUT/'criteria.json')
    result['gate_passed'] = all(c['predicted'] == criteria['expected'][c['id']] for c in result['cases'])
    result['model_s'] = sum(c.get('elapsed_s', 0) for c in result['cases'])
    write(OUT/'result.json', result)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['freeze', 'run'])
    args = parser.parse_args()
    OUT.mkdir(exist_ok=True, parents=True)
    freeze() if args.mode == 'freeze' else run()
