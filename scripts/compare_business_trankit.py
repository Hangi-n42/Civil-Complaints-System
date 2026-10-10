"""Issue 648: one pinned Trankit Korean-KAIST parse on the unchanged #646 units."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import business_dependency_parser as addresses

ROOT = addresses.ROOT
OUT = ROOT / 'data/knowledge/evaluations/business_trankit_20261010'
UNITS = ROOT / 'data/knowledge/evaluations/business_document_boundary_20261010'
read, write = addresses.read, addresses.write


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze():
    assert not (OUT / 'freeze.json').exists()
    assert sha(UNITS / 'inputs.json') == '6291df9299be771f71cb9d47ef6874279e24eae571af9c0c3609f0c598746d2c'
    config = dict(issue=648, source_commit='54e863327391262cf72f6adc1b0ff104e972a1dc',
        trankit='1.1.2', language='korean-kaist', treebank='UD_Korean-Kaist', model_version='v1.0.0',
        model_revision='1add34e3909949dbb98523ed6cfcb4e9393e2c8e', embedding='xlm-roberta-base',
        encoder_revision='e73636d4f797dec63c3081bb6ed5c7b0bb3f2089', device='cpu', threads=4,
        is_sent=True, seed=42, training=False, word_expansion=False,
        task='Same 24 unchanged document units, all parser output retained; no Qwen call authorized by this freeze',
        license='Code Apache-2.0; encoder card MIT; KAIST treebank CC BY-SA 4.0; separate task-weight license not stated in HF metadata or ZIP')
    write(OUT / 'parser_config.json', config)
    files = [UNITS / 'inputs.json', UNITS / 'parsed.json', Path(__file__), Path(addresses.__file__)]
    files += [OUT / n for n in ['parser_config.json', 'requirements.lock.txt', 'source_download.json',
                               'model_download.json', 'encoder_files.json', 'language_files.json', 'installed_code.json']]
    for receipt in ['encoder_files.json', 'language_files.json']:
        for row in read(OUT / receipt):
            p = OUT / row['file']; assert sha(p) == row['sha256']; files.append(p)
    write(OUT / 'freeze.json', dict(at=time.time(), maximum_documents=24, generation_calls=0,
        authorized_by='01a11fd9-f71b-7261-832b-0681548a03c4',
        files={str(p.relative_to(ROOT)): sha(p) for p in files}))


def map_tokens(raw, unit, original):
    if raw.get('text') != unit['text']:
        raise ValueError('raw_input_text_changed')
    mapped, covered = [], []
    for token in raw['tokens']:
        if not isinstance(token['id'], int) or 'expanded' in token:
            raise ValueError('unexpected_word_expansion')
        span = token.get('span')
        exact = addresses.exact_span(unit['text'], token['text'], *(span or [None, None]))
        global_span = None if exact is None else [n + unit['span'][0] for n in exact]
        if exact is not None:
            covered.append(exact)
            assert original[slice(*global_span)] == token['text']
        mapped.append(dict(token, exact_unit_span=exact, exact_original_span=global_span))
    assert all(t['head'] == 0 or t['head'] in {w['id'] for w in mapped} for t in mapped)
    return dict(tokens=mapped, uncovered=addresses.gaps(unit['text'], covered),
                unmapped=sum(t['exact_unit_span'] is None for t in mapped))


def run():
    assert not (OUT / 'parsed.json').exists()
    frozen = read(OUT / 'freeze.json')
    assert all(sha(ROOT / p) == h for p, h in frozen['files'].items())
    # Resolve the official encoder name to the pinned local directory, without patching the library.
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.chdir(OUT / 'runtime')
    import torch
    import trankit
    torch.set_num_threads(4)
    torch.manual_seed(42)
    start = time.perf_counter()
    pipeline = trankit.Pipeline('korean-kaist', cache_dir=str(OUT / 'models'), gpu=False, embedding='xlm-roberta-base')
    load_s = time.perf_counter() - start
    results = []
    for record in read(UNITS / 'inputs.json'):
        for unit in record['units']:
            start = time.perf_counter()
            with torch.no_grad():
                raw = pipeline(unit['text'], is_sent=True)
            elapsed = time.perf_counter() - start
            mapped = map_tokens(raw, unit, record['text'])
            results.append(dict(address=record['address'], unit=unit, raw=raw, mapped=mapped, parse_s=elapsed))
    assert len(results) == 24
    write(OUT / 'parsed.json', results)
    write(OUT / 'runtime.json', dict(documents=len(results), load_s=load_s,
        parse_s=sum(r['parse_s'] for r in results), tokens=sum(len(r['mapped']['tokens']) for r in results),
        unmapped=sum(r['mapped']['unmapped'] for r in results),
        nonwhitespace_gaps=sum(not g['whitespace_only'] for r in results for g in r['mapped']['uncovered']),
        torch=torch.__version__, trankit=trankit.__version__, device='cpu', threads=4, generation_calls=0))
    print(json.dumps(read(OUT / 'runtime.json'), indent=2))


def selfcheck():
    unit = dict(text='반복 반복', span=[3, 8])
    raw = dict(text=unit['text'], tokens=[dict(id=1, text='반복', span=[3, 5], head=0)])
    result = map_tokens(raw, unit, '앞쪽 ' + unit['text'])
    assert result['tokens'][0]['exact_original_span'] == [6, 8]
    raw['tokens'][0]['text'] = '다름'
    assert map_tokens(raw, unit, '앞쪽 ' + unit['text'])['unmapped'] == 1
    print('Supplied token positions, repeated text and unmatched surface preserved')


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['freeze', 'run', 'selfcheck'])
    globals()[cli.parse_args().mode]()
