"""Single local VitaminC checkpoint with reviewed translation; no product writes."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import time

from compare_business_nli import read, write, sha

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'data/knowledge/evaluations/business_nli_20261009'
OUT = ROOT / 'data/knowledge/evaluations/business_vitaminc_20261009'
MODEL = 'tals/albert-xlarge-vitaminc-mnli'
REVISION = '3082ba54344bd9ddada2be1c5e9b4131721d2a5d'
LABELS = ['SUPPORTS', 'REFUTES', 'NOT ENOUGH INFO']


def translated_pairs(translation, packet, originals):
    assert [(b['id'], b['ko']) for b in translation['blocks']] == [(b['id'], b['text']) for b in packet['blocks']]
    assert translation['source_parents'] == packet['source_parents']
    assert [(c['id'], c['ko']) for c in translation['candidates']] == [(c['id'], c['hypothesis']) for c in originals]
    assert all(b['en'].strip() for b in translation['blocks'])
    assert all(c['en'].strip() for c in translation['candidates'])
    premise = '\n'.join(b['en'] for b in translation['blocks'])
    return [dict(id=c['id'], premise=premise, hypothesis=c['en']) for c in translation['candidates']]


def freeze():
    assert not (OUT/'freeze.json').exists()
    review = read(OUT/'translation_review.json')
    assert review['verdict'] == 'pass' and not review['findings']
    assert sha(OUT/'translation_draft.json') == review['reviewed_file_sha256']
    write(OUT/'inputs.json', translated_pairs(read(OUT/'translation_draft.json'), read(BASE/'source_packet.json'), read(BASE/'inputs.json')))
    write(OUT/'criteria.json', dict(expected=dict(c13=LABELS[0], c46=LABELS[0], c47=LABELS[2], c11=LABELS[0]),
        gate='All four exact argmax labels, no tuning/retries; capacity/execution failures stay in denominator.',
        exposure='All four development-exposed; translation prepared and independently reviewed by agents, not human-certified.',
        boundary='Reviewed-translation label diagnostic only; not automatic translation, localization, correction or product completion.'))
    folder = Path(read(OUT/'download.json')['path'])
    assert folder.name == REVISION
    checkpoint = {str(p):sha(p) for p in folder.iterdir() if p.is_file()}
    write(OUT/'freeze.json', dict(model=MODEL, revision=REVISION, labels=LABELS,
        official_code_revision='eb532922b88b199df68ed26afeb58dca5501b52f',
        label_order='Official VitCFactVerificationProcessor and checkpoint config agree.',
        input_order='evidence first, claim second; full translated blocks in original order; parent metadata preserved separately.',
        device='cpu', dtype='float32', truncation=False, maximum_calls=4, single_pass=True,
        tokenizer='AutoTokenizer use_fast=False; official SentencePiece model',
        license='Official repository MIT; dataset separately licensed; weights card has no explicit license declaration.',
        files={str(p.relative_to(ROOT)):sha(p) for p in [OUT/'translation_draft.json', OUT/'translation_review.json',
            OUT/'inputs.json', OUT/'criteria.json', BASE/'inputs.json', BASE/'source_packet.json',
            Path(__file__), ROOT/'scripts/compare_business_nli.py']}, checkpoint=checkpoint,
        versions={n:importlib.metadata.version(n) for n in ['torch','transformers','safetensors','sentencepiece','huggingface-hub']}))


def run():
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer
    frozen = read(OUT/'freeze.json')
    assert all(sha(ROOT/p)==v for p,v in frozen['files'].items())
    assert all(sha(Path(p))==v for p,v in frozen['checkpoint'].items())
    assert not (OUT/'started.json').exists(), 'Single frozen execution only'
    folder = Path(read(OUT/'download.json')['path'])
    assert folder.name == REVISION
    config = read(folder/'config.json')
    assert config['id2label'] == {str(i):label for i,label in enumerate(LABELS)}
    tokenizer = AutoTokenizer.from_pretrained(folder, use_fast=False, local_files_only=True, trust_remote_code=False)
    pairs = read(OUT/'inputs.json')
    encoded = [tokenizer(p['premise'],p['hypothesis'],truncation=False,return_tensors='pt') for p in pairs]
    maximum = min(tokenizer.model_max_length, config['max_position_embeddings'])
    preflight = [dict(id=p['id'], token_count=e['input_ids'].shape[1],
        within_capacity=e['input_ids'].shape[1]<=maximum, encoded={k:v[0].tolist() for k,v in e.items()}) for p,e in zip(pairs,encoded)]
    write(OUT/'length_preflight.json', dict(maximum=maximum,truncation=False,cases=preflight))
    write(OUT/'started.json', dict(freeze_sha256=sha(OUT/'freeze.json')))
    result = dict(model=MODEL,revision=REVISION,cases=[],model_calls=0,gate_passed=False)
    try:
        started=time.monotonic()
        model=AutoModelForSequenceClassification.from_pretrained(folder, local_files_only=True,
            trust_remote_code=False,use_safetensors=True,torch_dtype=torch.float32).to('cpu').eval()
        result['load_s']=time.monotonic()-started
        for inputs,scope in zip(encoded,preflight):
            record=dict(scope,status='input_capacity',predicted=None)
            result['cases'].append(record)
            if scope['within_capacity']:
                started=time.monotonic()
                result['model_calls']+=1
                with torch.inference_mode():
                    logits=model(**inputs).logits[0]
                record.update(status='succeeded',elapsed_s=time.monotonic()-started,logits=logits.tolist(),
                    softmax=torch.softmax(logits,dim=-1).tolist(),argmax=int(logits.argmax()),predicted=LABELS[int(logits.argmax())])
            write(OUT/'result.json',result)
            print(record['id'],record['status'],record['predicted'],flush=True)
        expected=read(OUT/'criteria.json')['expected']
        result['gate_passed']=len(result['cases'])==len(expected) and all(c['predicted']==expected[c['id']] for c in result['cases'])
    except Exception as exc:
        result['execution_error']=repr(exc)
        raise
    finally:
        present={c['id'] for c in result['cases']}
        result['cases'].extend(dict(id=p['id'],status='not_completed',predicted=None) for p in pairs if p['id'] not in present)
        result['model_s']=sum(c.get('elapsed_s',0) for c in result['cases'])
        write(OUT/'result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['freeze','run'])
    args=parser.parse_args()
    freeze() if args.mode=='freeze' else run()
