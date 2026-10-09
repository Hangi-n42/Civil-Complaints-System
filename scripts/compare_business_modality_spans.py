"""Issue 636: one frozen local span diagnostic, with no product writes."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import re
import time
import urllib.request

from compare_business_nli import read, write, sha

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/knowledge/evaluations/business_modality_research_20261009'
MODEL = 'KRLabsOrg/lettucedect-v2-qwen-2b'
REVISION = '4511d95c6a5f24df1e810a097685d068208cb149'
CATEGORIES = {'contradiction', 'fabricated_reference', 'unsupported_addition'}
SUBCATEGORIES = {'entity', 'temporal', 'numerical', 'value', 'relational', 'identifier',
                 'section', 'attribute', 'claim', 'behavior', 'elaboration', 'subjective', 'unspecified'}
VERSIONS = ['torch', 'transformers', 'accelerate', 'safetensors', 'tokenizers', 'huggingface-hub']


def official_prompt():
    card = (OUT / 'model/README.md').read_text()
    matches = re.findall(r'SYSTEM_EXPL = """(.*?)"""', card, re.DOTALL)
    assert len(matches) == 1
    return matches[0]


def raw_fields(value, path='raw'):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from raw_fields(item, path + '.' + key)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from raw_fields(item, f'{path}[{index}]')


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate_json_key')
        result[key] = value
    return result


def parse_spans(text, case, answer):
    parsed = json.loads(text, object_pairs_hook=strict_object)
    if not isinstance(parsed, dict) or set(parsed) != {'hallucinated_spans'}:
        raise ValueError('root_contract')
    spans = parsed['hallucinated_spans']
    if not isinstance(spans, list):
        raise ValueError('span_list_contract')
    located = []
    for span in spans:
        if not isinstance(span, dict) or set(span) != {'text', 'category', 'subcategory', 'explanation'}:
            raise ValueError('span_contract')
        if any(not isinstance(span[k], str) or not span[k].strip() for k in span):
            raise ValueError('empty_span_or_reason')
        if span['category'] not in CATEGORIES or span['subcategory'] not in SUBCATEGORIES:
            raise ValueError('taxonomy_contract')
        quote = span['text']
        positions = [(path, match.start(), match.end()) for path, value in raw_fields(case['raw'])
                     for match in re.finditer('(?=' + re.escape(quote) + ')', value)]
        # Lookahead finds overlapping duplicates; compute the non-empty span end explicitly.
        positions = [(p, start, start + len(quote)) for p, start, _ in positions]
        if quote not in answer or len(positions) != 1:
            raise ValueError('missing_or_ambiguous_candidate_span')
        path, start, end = positions[0]
        located.append(dict(span, field=path, start_char=start, end_char=end))
    return dict(spans=located, native_types=sorted({s['category'] for s in located}),
                empty_span_list=not located, insufficient_source_status='not_in_native_contract',
                semantic_review='pending', automatic_source_evidence=False)


def prepare():
    from tokenizers import Tokenizer
    from transformers import AutoTokenizer
    assert not (OUT / 'messages.json').exists()
    tokenizer = AutoTokenizer.from_pretrained(OUT / 'model', local_files_only=True, trust_remote_code=False,
                                               fix_mistral_regex=False)
    original_tokenizer = Tokenizer.from_file(str(OUT / 'model/tokenizer.json'))
    system = official_prompt()
    rows = []
    for case in read(OUT / 'development_inputs.json'):
        context = {k: v for k, v in case.items() if k not in {'id', 'raw'}}
        answer = json.dumps(case['raw'], ensure_ascii=False, indent=2)
        user = 'User request: Verify the candidate statements against the provided source.\n\n'
        user += json.dumps(context, ensure_ascii=False, indent=2) + '\n\nAnswer to verify:\n' + answer
        messages = [dict(role='system', content=system), dict(role='user', content=user)]
        formatted = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True,
                                                  enable_thinking=False)
        ids = tokenizer(formatted, add_special_tokens=False, truncation=False)['input_ids']
        assert ids == tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                   enable_thinking=False, return_dict=False)
        assert ids == original_tokenizer.encode(formatted, add_special_tokens=False).ids
        rows.append(dict(id=case['id'], answer=answer, messages=messages, formatted=formatted,
                         input_ids=ids, input_tokens=len(ids)))
    write(OUT / 'messages.json', rows)
    write(OUT / 'tokenizer_preflight.json', dict(model=MODEL, revision=REVISION,
          input_lengths={r['id']: r['input_tokens'] for r in rows}, thinking=False, truncation=False,
          chat_template=tokenizer.chat_template, original_tokenizer_ids_equal=True,
          fix_mistral_regex=False,
          versions={v: importlib.metadata.version(v) for v in VERSIONS}))


def freeze():
    assert not (OUT / 'freeze.json').exists()
    probe = read(OUT / 'probe/result.json')
    assert probe['cases'][0]['generation_complete'] and probe['cases'][0]['format_pass']
    assert read(OUT / 'compute_allocation.json')['coordinator_allocated']
    settings = read(OUT / 'settings.json')
    assert max(r['input_tokens'] for r in read(OUT / 'messages.json')) + settings['generation']['max_new_tokens'] <= settings['context_limit']
    paths = ['development_inputs.json', 'input_origin_manifest.json', 'messages.json', 'criteria.json',
             'settings.json', 'tokenizer_preflight.json', 'model-download-receipt.json',
             'compute_allocation.json', 'probe/result.json', 'probe_comparison.json',
             'runtime-freeze.txt', 'runtime_repair.json', 'eos_contract_repair.json',
             'input_integrity_recheck.json']
    write(OUT / 'freeze.json', dict(model=MODEL, revision=REVISION, issue=636, frozen_at=time.time(),
          files={p: sha(OUT / p) for p in paths},
          code={str(p.relative_to(ROOT)): sha(p) for p in [Path(__file__), ROOT / 'scripts/compare_business_nli.py']},
          versions={v: importlib.metadata.version(v) for v in VERSIONS},
          max_semantic_calls=22, repeated_development=True, unused_confirmation_cases=0,
          baseline='Historical Qwen results only; matched-prompt A conditional on B semantic gate.'))


def run(phase):
    # MPS copy/cast crashed in parallel loader threads; serialize materialization only.
    os.environ['HF_DEACTIVATE_ASYNC_LOAD'] = '1'
    import resource
    import torch
    from transformers import AutoTokenizer, Qwen3_5ForConditionalGeneration, set_seed

    assert read(OUT / 'compute_allocation.json')['coordinator_allocated']
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps', timeout=10) as response:
        assert not json.load(response)['models'], 'Other Ollama model is loaded'
    settings = read(OUT / 'settings.json')
    if phase == 'development':
        frozen = read(OUT / 'freeze.json')
        assert all(sha(OUT / p) == h for p, h in frozen['files'].items())
        assert all(sha(ROOT / p) == h for p, h in frozen['code'].items())
        assert frozen['versions'] == {v: importlib.metadata.version(v) for v in VERSIONS}
    receipt = read(OUT / 'model-download-receipt.json')
    assert receipt['revision'] == REVISION
    assert all(sha(Path(f['path'])) == f['sha256'] for f in receipt['files'])
    dest = OUT / phase
    dest.mkdir()  # Never overwrite a previous attempt.
    result = dict(model=MODEL, revision=REVISION, phase=phase, started_at=time.time(), calls=0, cases=[],
                  settings=settings, semantic_gate='not_evaluated', total_wall_s=None)
    write(dest / 'result.json', result)
    started = time.monotonic()
    model = None
    try:
        set_seed(settings['seed'])
        tokenizer = AutoTokenizer.from_pretrained(OUT / 'model', local_files_only=True, trust_remote_code=False,
                                                   fix_mistral_regex=False)
        model = Qwen3_5ForConditionalGeneration.from_pretrained(
            OUT / 'model', dtype=torch.bfloat16, device_map={'': settings['device']},
            local_files_only=True, trust_remote_code=False, use_safetensors=True,
            attn_implementation='sdpa').eval()
        assert tokenizer.eos_token_id in settings['generation']['eos_token_id']
        assert model.generation_config.eos_token_id in settings['generation']['eos_token_id']
        result['termination_contract'] = dict(tokenizer_eos=tokenizer.eos_token_id,
            model_eos=model.generation_config.eos_token_id, actual=settings['generation']['eos_token_id'])
        torch.mps.synchronize()
        result['load_s'] = time.monotonic() - started
        result['parameters'] = sorted({(str(p.device), str(p.dtype)) for p in model.parameters()})
        if phase == 'probe':
            # Official model-card compatibility example, excluded from semantic scores.
            answer = 'The capital of France is Paris. Its population is 2 million.'
            messages = [dict(role='system', content=official_prompt()), dict(role='user', content=
                'User request: What is the capital of France? What is its population?\n\n'
                'France is a country in Europe. Its capital is Paris.\n\nAnswer to verify:\n' + answer)]
            ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                                                 enable_thinking=False, return_dict=False)
            rows = [dict(id='official_compatibility', answer=answer, messages=messages, input_ids=ids, input_tokens=len(ids))]
            cases = {rows[0]['id']: dict(raw={'Event': answer})}
        else:
            rows = read(OUT / 'messages.json')
            cases = {c['id']: c for c in read(OUT / 'development_inputs.json')}
        write(dest / 'requests.json', rows)
        for row in rows:
            record = dict(id=row['id'], status='started', input_tokens=row['input_tokens'], format_pass=False)
            result['cases'].append(record)
            write(dest / 'result.json', result)
            assert row['input_tokens'] + settings['generation']['max_new_tokens'] <= settings['context_limit']
            tokens = torch.tensor([row['input_ids']], device=settings['device'])
            torch.mps.synchronize()
            before = time.monotonic()
            result['calls'] += 1
            with torch.inference_mode():
                output = model.generate(input_ids=tokens, attention_mask=torch.ones_like(tokens),
                                        **settings['generation'])
            torch.mps.synchronize()
            generated = output[0, tokens.shape[1]:].tolist()
            record.update(elapsed_s=time.monotonic() - before, output_ids=generated, output_tokens=len(generated),
                          raw_output=tokenizer.decode(generated, skip_special_tokens=True),
                          generation_complete=bool(generated and generated[-1] in settings['generation']['eos_token_id']),
                          rss_high_water_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                          mps_allocated_bytes=torch.mps.current_allocated_memory(),
                          mps_driver_bytes=torch.mps.driver_allocated_memory())
            if not record['generation_complete']:
                record['status'] = 'execution_incomplete'
            else:
                try:
                    record['parsed'] = parse_spans(record['raw_output'], cases[row['id']], row['answer'])
                    record.update(format_pass=True, status='completed')
                except (ValueError, TypeError) as error:
                    record.update(status='format_failure', format_error=str(error))
            write(dest / f"{row['id']}.json", record)
            write(dest / 'result.json', result)
            print(row['id'], record['status'], record['output_tokens'], round(record['elapsed_s'], 3), flush=True)
            del output, tokens
            torch.mps.empty_cache()
    except Exception as error:
        result['fatal_error'] = repr(error)
        raise
    finally:
        result['total_wall_s'] = time.monotonic() - started
        write(dest / 'result.json', result)
        if model is not None:
            del model
        torch.mps.empty_cache()


def selfcheck():
    case = dict(raw={'Event': '검사 구절', 'Entity': ['중복', '중복']})
    span = dict(text='구절', category='unsupported_addition', subcategory='claim', explanation='계약 검사')
    assert parse_spans(json.dumps({'hallucinated_spans': [span]}), case, '검사 구절')['spans'][0]['start_char'] == 3
    assert parse_spans('{"hallucinated_spans":[]}', case, '')['empty_span_list']
    for bad in ['', '{"hallucinated_spans":[],"hallucinated_spans":[]}',
                json.dumps({'hallucinated_spans': [dict(span, text='중복')]}),
                json.dumps({'hallucinated_spans': [dict(span, text='없음')]}),
                json.dumps({'hallucinated_spans': [dict(span, explanation='')]})]:
        try:
            parse_spans(bad, case, '검사 구절 중복 중복')
        except ValueError:
            continue
        raise AssertionError('invalid output accepted')
    print('span location / empty list vs empty response / duplicate JSON / missing or repeated quote / reason checks passed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'freeze', 'probe', 'development', 'selfcheck'])
    mode = parser.parse_args().mode
    if mode in {'probe', 'development'}:
        run(mode)
    else:
        globals()[mode]()
