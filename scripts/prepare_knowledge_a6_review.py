"""Prepare blind offline review cards and score separately adjudicated records; no model calls."""
import argparse
from html import escape
from hashlib import sha256
import json
import math
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_knowledge_a6 import ASSETS, check_freeze, write
from app.knowledge import discovery_inputs as inputs


def prepare(study, output):
    frozen = check_freeze()
    if json.loads((study/'study.json').read_text(encoding='utf-8'))['freeze'] != frozen:
        raise ValueError('다른 동결 조건의 평가 원장입니다.')
    spec = json.loads((ASSETS / 'reviewer_cards.json').read_text(encoding='utf-8'))
    manifest = json.loads(inputs.MANIFEST.read_text(encoding='utf-8'))
    allowed = {f'{s["source_id"]}:{n}':f['sha256'] for s in manifest['selected_sources']
               for n,f in enumerate(s['input_files'])}
    manifest_hash = sha256(inputs.MANIFEST.read_bytes()).hexdigest()
    files = {}
    block_hashes = {}
    for result in study.glob('*.json'):
        value = json.loads(result.read_text(encoding='utf-8'))
        run = value.get('input_run', {})
        if run and run['frozen_input']['manifest_hash'] != manifest_hash:
            raise ValueError('다른 manifest의 원문입니다.')
        block_hashes.update({b['id']: b['text_sha256'] for b in value.get('input_blocks', [])})
        for item, unit in zip(run.get('frozen_input', {}).get('files', []), run.get('units', [])):
            if unit['status'] == 'succeeded':
                if allowed.get(item['file_id']) != item['sha256']:
                    raise ValueError('동결 파일 해시 불일치')
                files[item['file_id']] = dict(item, block_ids=unit['block_ids'])
    needed = {i for row in spec['cards']+spec['requirements'] for i in row['file_ids']}
    if not needed <= files.keys():
        raise ValueError('완료된 A1 원문 필요: ' + ', '.join(sorted(needed-files.keys())))
    originals = {}
    # Only immutable blocks are read. Do not initialize a service or recover a running ledger.
    with sqlite3.connect((study / 'knowledge.db').resolve().as_uri() + '?mode=ro', uri=True) as db:
        for identifier in sorted(needed):
            originals[identifier] = dict(source=files[identifier], blocks=[json.loads(db.execute(
                'SELECT payload FROM blocks WHERE id=?', (block_id,)).fetchone()[0])
                for block_id in files[identifier]['block_ids']])
            if any(block_hashes.get(b['id']) != sha256(b['text'].encode()).hexdigest() or
                   b['source_version_id'] != files[identifier]['source_version_id']
                   for b in originals[identifier]['blocks']):
                raise ValueError('저장된 평가 블록의 버전/내용 불일치')
    output.mkdir(parents=True, exist_ok=False)
    write(output / 'sources.json', originals)
    write(output / 'freeze.json', frozen)
    for packet in ('A', 'B'):
        cards = [c for c in spec['cards'] if c['packet'] == packet]
        requirements = [r for r in spec['requirements'] if r['packet'] == packet]
        blind = [dict(id=c['id'], candidate=c['candidate'], file_ids=c['file_ids'], locator=c['locator']) for c in cards]
        missing = [{k:v for k,v in r.items() if k != 'rationale'} for r in requirements]
        write(output / (packet + '.json'), dict(cards=blind, requirements=missing))
        for condition in ('baseline', 'assisted'):
            html = ['<!doctype html><html lang="ko"><meta charset="utf-8"><title>A6 검수 카드</title>',
                    '<style>body{max-width:960px;margin:32px auto;font-family:sans-serif;line-height:1.6}pre{white-space:pre-wrap}article{border:1px solid #888;padding:16px;margin:16px 0}</style>',
                    f'<h1>{packet} / {condition}</h1><p>오프라인 카드 모의 시험. 원문·검색·diff·메타데이터·요약·수동 관계표 사용 가능.</p>',
                    '<p>정상/오류 표시는 공개하지 않음. 결정과 이유, 수정 문장, 열람/탐색 횟수, 실제 시간을 기록하세요.</p>']
            for card in blind:
                html.append(f'<article><h2>{card["id"]}</h2><p>{escape(card["candidate"])}</p>')
                if condition == 'assisted':
                    html.append(f'<p>근거 위치: {escape(card["locator"])}</p>')
                html.append('<p>원문: ' + ', '.join(escape(i) for i in card['file_ids']) + '</p></article>')
            html.append('<h2>요구와 후보 연결표</h2>')
            for req in missing:
                text = f'{req["id"]}: {req["question"]} / AI 표시: {req["claimed_status"]} / 연결: {req["candidate_ids"]}'
                html.append('<p>' + ('<strong>' if condition == 'assisted' else '') + escape(text)
                            + ('</strong>' if condition == 'assisted' else '') + '</p>')
            for identifier in sorted({i for c in cards+requirements for i in c['file_ids']}):
                source = originals[identifier]
                html.append(f'<details><summary>{escape(identifier)} 원문·위치</summary>')
                for b in source['blocks']:
                    html.append('<pre>' + escape(b['text']) + '</pre><small>' + escape(
                        json.dumps(dict(evidence_id=b['evidence_id'], locator=b['locator']), ensure_ascii=False)) + '</small>')
                html.append('</details>')
            html.append('</html>')
            (output / f'{packet}-{condition}.html').write_text('\n'.join(html), encoding='utf-8')
        write(output / (packet + '-record-template.json'), dict(participant_id=None, participant_kind=None,
            condition=None, packet=packet, preparation_s=None, cq_s=None, review_s=None, repair_s=None,
            rows=[dict(id=row['id'], decision=None, reason=None, corrected_text=None,
                       discovered=None, original_views=None, navigation_steps=None) for row in cards+requirements]))
        write(output / (packet + '-adjudication-template.json'), dict(adjudicator=None,
            rows=[dict(id=row['id'], discovery_correct=None, final_semantics=None, rationale=None) for row in cards+requirements]))


def score(record, adjudication, spec):
    """Human decisions and independent semantic grading are separate inputs."""
    if record['participant_kind'] not in {'human', 'ai'} or not record['participant_id']:
        raise ValueError('참가 종류와 익명 ID가 필요합니다.')
    if record['condition'] not in {'baseline', 'assisted'}:
        raise ValueError('시험 조건이 필요합니다.')
    if record['packet'] not in {'A','B'}:
        raise ValueError('시험 묶음이 필요합니다.')
    cards = {c['id']:c for c in spec['cards']+spec['requirements'] if c['packet'] == record['packet']}
    rows = record['rows']; grades = {r['id']:r for r in adjudication['rows']}
    if (len(rows) != len(cards) or {r['id'] for r in rows} != cards.keys() or
            len(adjudication['rows']) != len(cards) or grades.keys() != cards.keys()):
        raise ValueError('한 묶음 전체의 유일한 카드/요구 기록과 별도 판정이 필요합니다.')
    if not adjudication['adjudicator']:
        raise ValueError('최종 의미 판정자를 기록하세요.')
    totals = dict(error_found=0, correct_repair=0, error_rejected=0, error_deferred=0,
                  normal_intervention=0, normal_harmed=0, wrong_edit_approved=0,
                  remaining_core_error=0, unresolved_approval=0, unlinked_gap_found=0, false_fulfillment_found=0)
    for row in rows:
        truth = cards[row['id']]; grade = grades[row['id']]
        if row['decision'] not in {'approve', 'reject', 'modify_approve', 'defer'} or type(row['discovered']) is not bool:
            raise ValueError('결정과 발견 여부를 모두 기록하세요.')
        if (grade['final_semantics'] not in {'supported', 'refuted', 'unresolved'} or
                not grade['rationale'] or type(grade['discovery_correct']) is not bool):
            raise ValueError('최종 의미의 독립 판정과 근거가 필요합니다.')
        if row['decision']=='modify_approve' and not row['corrected_text']:
            raise ValueError('수정 후 승인에는 실제 수정 문장이 필요합니다.')
        for key in ('original_views','navigation_steps'):
            if row[key] is not None and (type(row[key]) is not int or row[key]<0):
                raise ValueError('열람·탐색 횟수는 비음수 정수 또는 미측정 null이어야 합니다.')
        approved = row['decision'] in {'approve', 'modify_approve'}
        error = truth.get('expected') == 'error'
        found = row['discovered'] and grade['discovery_correct']
        totals['error_found'] += int(error and found)
        totals['correct_repair'] += int(error and row['decision']=='modify_approve' and grade['final_semantics']=='supported')
        totals['error_rejected'] += int(error and row['decision']=='reject')
        totals['error_deferred'] += int(error and row['decision']=='defer')
        totals['normal_intervention'] += int(truth.get('expected')=='normal' and row['decision'] in {'reject','modify_approve'})
        totals['normal_harmed'] += int(truth.get('expected')=='normal' and
            (row['decision']=='reject' or row['decision']=='modify_approve' and grade['final_semantics']=='refuted'))
        totals['wrong_edit_approved'] += int(row['decision']=='modify_approve' and grade['final_semantics']=='refuted')
        totals['remaining_core_error'] += int(approved and grade['final_semantics']=='refuted')
        totals['unresolved_approval'] += int(approved and grade['final_semantics']=='unresolved')
        totals['unlinked_gap_found'] += int(row['id']=='M1' and found)
        totals['false_fulfillment_found'] += int(row['id']=='M2' and found)
    times = {k:record[k] for k in ('preparation_s','cq_s','review_s','repair_s')}
    if any(v is not None and (isinstance(v, bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0) for v in times.values()):
        raise ValueError('시간은 실제 비음수 초 또는 미측정 null이어야 합니다.')
    return dict(participant_id=record['participant_id'], participant_kind=record['participant_kind'],
        condition=record['condition'], packet=record['packet'], counts=totals,
        denominators=dict(normal=2, error=2, missing=1), human_times=times if record['participant_kind']=='human' else None,
        reported_times=times, efficacy_claim='단일 기록은 비교 효과 입증 아님',
        original_views=[r['original_views'] for r in rows], navigation_steps=[r['navigation_steps'] for r in rows])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','score'])
    parser.add_argument('--study', type=Path)
    parser.add_argument('--record', type=Path)
    parser.add_argument('--adjudication', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'prepare':
        if not args.study: parser.error('--study 필요')
        prepare(args.study, args.output)
    else:
        if not args.record or not args.adjudication: parser.error('--record와 --adjudication 필요')
        check_freeze()
        read = lambda p: json.loads(p.read_text(encoding='utf-8'))
        write(args.output, score(read(args.record), read(args.adjudication), read(ASSETS/'reviewer_cards.json')))


if __name__ == '__main__':
    main()
