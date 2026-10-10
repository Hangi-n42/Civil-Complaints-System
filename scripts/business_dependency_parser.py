"""Research-only Stanza output and exact raw-character addresses; no semantic rules."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/knowledge/evaluations/business_dependency_parser_20261010'
BASE = ROOT / 'data/knowledge/evaluations/business_direct_selection_structure_20261010'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def strings(value, path=()):
    if isinstance(value, str):
        yield list(path), value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from strings(item, (*path, key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from strings(item, (*path, index))


def exact_span(text, surface, start, end):
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(text):
        if text[start:end] == surface:
            return [start, end]
    return None


def gaps(text, spans):
    covered = set()
    for start, end in spans:
        covered.update(range(start, end))
    result = []
    for index, char in enumerate(text):
        if index not in covered:
            if result and result[-1][1] == index:
                result[-1][1] += 1
            else:
                result.append([index, index + 1])
    return [dict(span=s, text=text[s[0]:s[1]], whitespace_only=text[s[0]:s[1]].isspace()) for s in result]


def mapped_document(doc, text):
    assert doc.text == text
    sentences, spans = [], []
    for sentence in doc.sentences:
        tokens, words = [], []
        for number, token in enumerate(sentence.tokens, 1):
            span = exact_span(text, token.text, token.start_char, token.end_char)
            if span is not None:
                spans.append(span)
            tokens.append(dict(index=number, ids=list(token.id), text=token.text,
                               reported_span=[token.start_char, token.end_char], exact_span=span))
            for word in token.words:
                words.append(dict(id=word.id, text=word.text, lemma=word.lemma, upos=word.upos,
                                  xpos=word.xpos, feats=word.feats, head=word.head, deprel=word.deprel,
                                  token_index=number, reported_span=[word.start_char, word.end_char],
                                  exact_span=exact_span(text, word.text, word.start_char, word.end_char)))
        assert all(w['head'] == 0 or w['head'] in {v['id'] for v in words} for w in words)
        sentences.append(dict(text=sentence.text, tokens=tokens, words=words))
    return dict(sentences=sentences, uncovered=gaps(text, spans),
                token_unmapped=sum(t['exact_span'] is None for s in sentences for t in s['tokens']),
                word_unmapped=sum(w['exact_span'] is None for s in sentences for w in s['words']))


def compact(record):
    # Keep every token/word and every dependency. Token span is not a lemma span.
    sentences = []
    for sentence in record['mapped']['sentences']:
        tokens, words = sentence['tokens'], sentence['words']
        shared = len(tokens) == len(words) and all(
            t['ids'] == [w['id']] == [i] and t['index'] == w['token_index'] == i
            and t['text'] == w['text'] and t['exact_span'] == w['exact_span']
            and t['exact_span'] is not None and w['feats'] is None
            and all(isinstance(w[k], str) and not any(c in w[k] for c in '\t\n')
                    for k in ('text', 'lemma', 'upos', 'xpos', 'deprel'))
            for i, (t, w) in enumerate(zip(tokens, words), 1))
        if shared:
            sentences.append(dict(encoding='shared_token_word_tsv', feats=None,
                rows='\n'.join('\t'.join([str(w['exact_span'][0]), str(w['exact_span'][1]), w['text'], w['lemma'],
                               w['upos'], w['xpos'], str(w['head']), w['deprel']]) for w in words)))
        else:
            sentences.append(dict(encoding='separate', tokens=tokens, words=words))
    return dict(address={k: v for k, v in record['address'].items() if k != 'original'},
                sentences=sentences,
                uncovered=record['mapped']['uncovered'])


def expand_sentence(sentence):
    if sentence['encoding'] == 'separate':
        return sentence['tokens'], sentence['words']
    tokens, words = [], []
    for index, row in enumerate(sentence['rows'].splitlines(), 1):
        start, end, text, lemma, upos, xpos, head, deprel = row.split('\t')
        span = [int(start), int(end)]
        tokens.append(dict(index=index, ids=[index], text=text, reported_span=span, exact_span=span))
        words.append(dict(id=index, text=text, lemma=lemma, upos=upos, xpos=xpos,
                          feats=sentence['feats'], head=int(head), deprel=deprel, token_index=index,
                          reported_span=span, exact_span=span))
    return tokens, words


def parse():
    import stanza
    import torch
    assert not (OUT / 'parsed.json').exists()
    config = read(OUT / 'parser_config.json')
    assert stanza.__version__ == config['stanza_version']
    torch.set_num_threads(config['threads'])
    start = time.perf_counter()
    nlp = stanza.Pipeline(lang='ko', dir=str(OUT / 'models'), package='kaist',
                          processors=config['processors'], use_gpu=False, download_method=None)
    load_s = time.perf_counter() - start
    cases = [c for c in read(BASE / 'inputs.json') if c['id'] in ['c47', 'c13', 'c46']]
    originals = read(BASE / 'originals.json')
    assert all(c['blocks'] == cases[0]['blocks'] for c in cases)
    inputs = [dict(address=dict(kind='source', block_id=b['id'], original=originals['c47'][b['id']]),
                   text=b['text']) for b in cases[0]['blocks']]
    for case in cases:
        inputs.extend(dict(address=dict(kind='candidate', case_id=case['id'], field_path=path), text=text)
                      for path, text in strings(case['raw']))
    records = []
    for item in inputs:
        start = time.perf_counter()
        doc = nlp(item['text'])
        record = dict(**item, text_sha256=digest(item['text']), parse_s=time.perf_counter() - start,
                      raw=doc.to_dict(), mapped=mapped_document(doc, item['text']))
        records.append(record)
    write(OUT / 'parsed.json', records)
    write(OUT / 'parser_runtime.json', dict(stanza=stanza.__version__, torch=torch.__version__,
          python=platform.python_version(), platform=platform.platform(), device='cpu',
          threads=torch.get_num_threads(), load_s=load_s, parse_s=sum(r['parse_s'] for r in records),
          documents=len(records), input_characters=sum(len(r['text']) for r in records),
          token_unmapped=sum(r['mapped']['token_unmapped'] for r in records),
          word_unmapped=sum(r['mapped']['word_unmapped'] for r in records),
          nonwhitespace_gaps=[dict(address=r['address'], gap=g) for r in records
                              for g in r['mapped']['uncovered'] if not g['whitespace_only']]))
    print(json.dumps(read(OUT / 'parser_runtime.json'), ensure_ascii=False, indent=2))


def selfcheck():
    # Repeated surfaces must retain supplied positions; never repair with str.find().
    assert exact_span('반복 반복', '반복', 3, 5) == [3, 5]
    assert exact_span('반복 반복', '반복', 2, 4) is None
    assert exact_span('갔다', '가다', 0, 2) is None
    assert exact_span('한글', '한글', None, None) is None
    assert gaps('가\n\t(나)', [[0, 1], [4, 5]]) == [
        dict(span=[1, 4], text='\n\t(', whitespace_only=False),
        dict(span=[5, 6], text=')', whitespace_only=False)]
    assert list(strings({'Head': '가', 'Entity': ['나']})) == [(['Head'], '가'), (['Entity', 0], '나')]
    print('Exact offsets, repeated surfaces, unmatched lemmas, gaps, original field boundaries passed')


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['selfcheck', 'parse'])
    globals()[cli.parse_args().mode]()
