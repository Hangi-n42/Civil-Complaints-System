"""Issue 646: one frozen Stanza parse over exact, DOM-supported document units."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import time

import business_dependency_parser as previous

ROOT = previous.ROOT
OUT = ROOT / 'data/knowledge/evaluations/business_document_boundary_20261010'
read, write = previous.read, previous.write


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore(mapped, unit, original):
    result = deepcopy(mapped)
    offset = unit['span'][0]
    assert original[slice(*unit['span'])] == unit['text']
    for sentence in result['sentences']:
        for item in sentence['tokens'] + sentence['words']:
            for key in ['reported_span', 'exact_span']:
                if item[key] is not None:
                    item[key] = [None if n is None else n + offset for n in item[key]]
            if item['exact_span'] is not None:
                assert original[slice(*item['exact_span'])] == item['text']
    for gap in result['uncovered']:
        gap['span'] = [n + offset for n in gap['span']]
        assert original[slice(*gap['span'])] == gap['text']
    return result


def freeze():
    assert not (OUT / 'freeze.json').exists()
    assert sha(OUT / 'inputs.json') == '6291df9299be771f71cb9d47ef6874279e24eae571af9c0c3609f0c598746d2c'
    config = dict(read(previous.OUT / 'parser_config.json'), tokenize_no_ssplit=True,
                  call_unit='Each unchanged substring separately; local offsets restored to original block/field')
    write(OUT / 'parser_config.json', config)
    write(OUT / 'criteria.json', dict(issue=646,
        gates=['Exact original substrings, metadata/parents/fields preserved; no new text.',
               'Removal of cross-note dependencies is necessary but not sufficient.',
               'Review regional scope and return/change relationship, outer required items and inner obligation.',
               'Review normal missing-buyer parent, document lists and corporate alternative.',
               'No Qwen call without coordinator finding needed information improved.'],
        baseline='Preserved #645 raw parses; no reparsing or semantic edits',
        changed='DOM-supported separate documents and official no_ssplit; same trained weights and POS system',
        maximum_documents=24, source_units=11, candidate_units=13))
    files = [OUT / n for n in ['inputs.json', 'source.html', 'parser_config.json', 'criteria.json',
                              'exposure_inventory.json', 'preparation.json']]
    files += [previous.OUT / 'parsed.json', previous.OUT / 'model_files.json', Path(previous.__file__),
              Path(__file__), ROOT / 'scripts/business_document_units.py']
    write(OUT / 'freeze.json', dict(at=time.time(), authorized_by='01a11fd9-f71b-7261-832b-0681548a03c4',
          files={str(p.relative_to(ROOT)): sha(p) for p in files}, parser_documents=24, generation_calls=0))


def run():
    import stanza
    import torch
    assert not (OUT / 'parsed.json').exists()
    frozen = read(OUT / 'freeze.json')
    assert all(sha(ROOT / p) == h for p, h in frozen['files'].items())
    for model in read(previous.OUT / 'model_files.json'):
        assert sha(previous.OUT / 'models' / model['path']) == model['sha256']
    config = read(OUT / 'parser_config.json')
    assert stanza.__version__ == config['stanza_version']
    torch.set_num_threads(4)
    start = time.perf_counter()
    pipeline = stanza.Pipeline(lang='ko', dir=str(previous.OUT / 'models'), package='kaist',
        processors=config['processors'], use_gpu=False, download_method=None, tokenize_no_ssplit=True)
    load_s = time.perf_counter() - start
    results = []
    for original in read(OUT / 'inputs.json'):
        for unit in original['units']:
            start = time.perf_counter()
            doc = pipeline(unit['text'])
            elapsed = time.perf_counter() - start
            local = previous.mapped_document(doc, unit['text'])
            results.append(dict(address=original['address'], unit=unit, raw=doc.to_dict(),
                mapped_local=local, mapped_original=restore(local, unit, original['text']), parse_s=elapsed))
    assert len(results) == 24
    write(OUT / 'parsed.json', results)
    write(OUT / 'runtime.json', dict(stanza=stanza.__version__, torch=torch.__version__, device='cpu',
        threads=4, documents=len(results), load_s=load_s, parse_s=sum(r['parse_s'] for r in results),
        token_unmapped=sum(r['mapped_local']['token_unmapped'] for r in results),
        word_unmapped=sum(r['mapped_local']['word_unmapped'] for r in results),
        nonwhitespace_gaps=sum(not g['whitespace_only'] for r in results for g in r['mapped_local']['uncovered']),
        new_generation_calls=0))
    print(json.dumps(read(OUT / 'runtime.json'), indent=2))


if __name__ == '__main__':
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['freeze', 'run'])
    globals()[cli.parse_args().mode]()
