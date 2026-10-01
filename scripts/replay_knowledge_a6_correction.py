"""Replay selected stored A6 contexts without models or ledger writes; not a quality evaluation."""
import argparse
import ast
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.knowledge import discovery_analysis as a2, discovery_profile as profile
from scripts.run_knowledge_a6 import ROOT, digest
from scripts.prepare_knowledge_a6_review import canonical_hash, review_freeze


def baseline_functions(commit):
    """Load only historical constants and the pure compact function from the specified Git object."""
    read = lambda name: subprocess.check_output(['git', 'show', commit + ':' + name], cwd=ROOT, text=True)
    constants = {}
    for node in ast.parse(read('app/knowledge/discovery_models.py')).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'COMMON', 'PROMPTS'} for t in node.targets):
            constants[node.targets[0].id] = ast.literal_eval(node.value)
    node = next(n for n in ast.parse(read('app/knowledge/discovery_analysis.py')).body
                if isinstance(n, ast.FunctionDef) and n.name == 'compact')
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<historical compact>', 'exec'), namespace)
    return constants, namespace['compact']


def raw_packets(value):
    if isinstance(value, list): return [b for v in value for b in raw_packets(v)]
    if isinstance(value, dict):
        if 'ref' in value and 'text' in value: return [value]
        return [b for v in value.values() for b in raw_packets(v)]
    return []


def replay(study, baseline):
    frozen = review_freeze(study)
    correction_path = ROOT / 'configs/knowledge/a6_correction_20261001.json'
    correction = json.loads(correction_path.read_text(encoding='utf-8'))
    if baseline != correction['baseline_commit'] or any(digest(ROOT / name) != expected for name, expected in correction['sha256'].items()):
        raise ValueError('correction 코드/기준 버전 불일치')
    constants, old_compact = baseline_functions(baseline)
    paths = [study / name for name in ('knowledge.db', 'study.json', 'contrast.json', 'history0.json', 'history2.json')]
    before = {p.name: digest(p) for p in paths}
    results, capacities = [], []
    for name in ('contrast', 'history0', 'history2'):
        value = json.loads((study / (name + '.json')).read_text(encoding='utf-8'))
        run = value['run']; blocks = []
        with sqlite3.connect((study / 'knowledge.db').resolve().as_uri() + '?mode=ro', uri=True) as db:
            for file, unit in zip(run['frozen_input']['files'], run['units']):
                for n, bid in enumerate(unit.get('block_ids', [])):
                    block = json.loads(db.execute('SELECT payload FROM blocks WHERE id=?', (bid,)).fetchone()[0])
                    blocks.append(dict(block, file_id=file['file_id'], title=file['title'], role=file.get('role'),
                        source_group=file['manifest_source_id'], source_id=file['source_id'], block_index=n))
        expected = {b['id']: b['text_sha256'] for b in value['input_blocks']}
        assert all(expected[b['id']] == canonical_text_hash(b['text']) for b in blocks)
        by_id = {b['id']: b for b in blocks}; context_map = {}
        for file in run['frozen_input']['files']:
            context_map.update(profile.contexts([b for b in blocks if b['file_id'] == file['file_id']]))

        def capture(service, current, stage, key, context, deps, by_id, supplied=None):
            unit = next(u for u in run['analysis_units'] if u['id'] == stage + ':' + key)
            mapping, prompt = a2.make_prompt(current, stage, context, deps, supplied or {})
            payload = dict(cqs=current['cqs'], scope_items=current['scope_items'], **context)
            old_prompt = constants['COMMON'] + constants['PROMPTS'][stage] + '\nINPUT:\n' + json.dumps(
                a2.remap(old_compact(payload), mapping), ensure_ascii=False, separators=(',', ':'))
            compacted = a2.compact(payload)
            assert raw_packets(compacted) == raw_packets(payload)
            assert a2.raw_refs(compacted) == a2.raw_refs(payload)
            for candidate in context.get('reviewed_base', []):
                for evidence in candidate['evidence']:
                    actual = next(c for c in compacted['reviewed_base'] if c['id'] == candidate['id'])
                    other = next(e for e in actual['evidence'] if e['evidence_id'] == evidence['evidence_id'])
                    assert {k:v for k,v in evidence.items() if k != 'quote'} == {k:v for k,v in other.items() if k != 'quote'}
            results.append(dict(case=name, unit_id=unit['id'], stored_status=unit['status'],
                stored_error=unit.get('error'), old_prompt_chars=len(old_prompt), correction_prompt_chars=len(prompt),
                char_limit=current['recipe']['input_chars'], correction_within_char_limit=len(prompt)<=current['recipe']['input_chars'],
                correction_within_token_upper_bound=len(prompt.encode())+current['recipe']['num_predict']<=current['recipe']['num_ctx'],
                historical_input_hash_matches=unit.get('input_hash') == profile.digest([old_prompt, current['recipe']]) if unit.get('input_hash') else None,
                raw_refs=sorted(a2.raw_refs(payload)), raw_packet_sha256=canonical_hash(raw_packets(payload)),
                raw_text_locator_and_refs_preserved=True))
            return deepcopy(unit.get('output'))

        def forbidden(*args, **kwargs):
            raise AssertionError('Replay must not call a model')

        current = deepcopy(run); current['metrics']['llm_calls'] = 0
        with patch.object(a2, 'allowed_ids', lambda *args: set(by_id)), patch.object(a2, 'call', capture), \
                patch.object(a2, 'apply_actions', lambda *args: None), patch.object(a2, 'save', lambda *args: None), \
                patch.object(a2, 'model_call', forbidden):
            for group in current['frontier']:
                a2.process_group(None, current, group, None, blocks, by_id, context_map)
            a2.finish(current, blocks, set(by_id))
        capacities.append(dict(case=name, status=current['status'], capacity_pending=current['result']['capacity_pending'],
            raw_provided=current['result']['raw_provided'], evidence_linked=len(current['result']['evidence_linked_block_ids']),
            processed_analysis_groups=current['result']['processed_analysis_groups']))
    assert before == {p.name: digest(p) for p in paths}
    return dict(kind='stored-context-replay', generation_http_calls=0, participant_count=0,
        historical_freeze_id=frozen['id'], baseline_commit=baseline,
        correction_id=correction['id'], correction_sha256=digest(correction_path), prompt_version=a2.PROMPT_VERSION,
        storage_before_and_after=before, storage_unchanged=True, contexts=results, capacities=capacities,
        limitation='저장 출력의 입력 구성/상태 재현; 새 모델의 의미 정확성이나 누락 개선 측정 아님')


def canonical_text_hash(text):
    from hashlib import sha256
    return sha256(text.encode('utf-8')).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--baseline', default='24f7acd2bd7fb1b95f885c491ac56c84d06dddce')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Reserve output before reading; never overwrite earlier replay evidence.
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(replay(args.study, args.baseline), stream, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
