"""Actual version diff plus direct and newly relevant requirement reassessment."""
from difflib import SequenceMatcher
import json
from time import monotonic
from uuid import uuid4

from pydantic import BaseModel
from typing import Literal

from app.core.config import settings
from app.generation.model_client import configuration, ModelClient
from . import autoschema, business_run, business_review
from .service import KnowledgeConflict, encode, utcnow


class Impact(BaseModel):
    requirement_id: str
    status: Literal['affected', 'unaffected', 'unknown']
    reason: str
    change_ids: list[str]
    new_relevance: bool


class Impacts(BaseModel):
    items: list[Impact]


def differences(before, after, key_fields):
    changes, unchanged = [], []
    if key_fields:
        def indexed(blocks):
            result = {}
            for b in blocks:
                fields = b['locator'].get('fields', {})
                if any(k not in fields for k in key_fields):
                    raise ValueError('변경 비교의 키 열이 없습니다.')
                key = tuple(str(fields[k]) for k in key_fields)
                if key in result:
                    raise ValueError('변경 비교 키가 중복됩니다.')
                result[key] = b
            return result
        old, new = indexed(before), indexed(after)
        for key in sorted(set(old) | set(new)):
            a, b = old.get(key), new.get(key)
            av, bv = a['locator']['fields'] if a else {}, b['locator']['fields'] if b else {}
            fields = [dict(field=k, before=av.get(k), after=bv.get(k)) for k in sorted(set(av) | set(bv)) if av.get(k) != bv.get(k)]
            item = dict(key=list(key), before_block_id=a['id'] if a else None, after_block_id=b['id'] if b else None,
                        before=av, after=bv, fields=fields)
            if fields:
                changes.append(dict(item, id=uuid4().hex, kind='added' if not a else 'removed' if not b else 'modified'))
            else:
                unchanged.append(item)
    else:
        matcher = SequenceMatcher(a=[b['text'] for b in before], b=[b['text'] for b in after], autojunk=False)
        for kind, i, j, p, q in matcher.get_opcodes():
            if kind == 'equal':
                unchanged.extend(dict(before_block_id=a['id'], after_block_id=b['id'], text=a['text']) for a, b in zip(before[i:j], after[p:q]))
            else:
                changes.append(dict(id=uuid4().hex, kind=kind, before=before[i:j], after=after[p:q],
                                    before_block_ids=[b['id'] for b in before[i:j]], after_block_ids=[b['id'] for b in after[p:q]]))
    return dict(changes=changes, unchanged=unchanged, comparison='exact_row_values' if key_fields else 'ordered_source_text')


def stored_dependencies(service, requirements):
    """Read the exact assessment behind each pointer, retaining its semantic limits."""
    records, blocks = [], {}
    with service.repository.connect() as db:
        for requirement in requirements:
            pointer = requirement.get('current_assessment')
            record = dict(requirement_id=requirement['id'], assessment_pointer={k: pointer[k] for k in
                          ('run_id', 'assessment_id', 'revision', 'source_version_ids')} if pointer else None,
                          status='unassessed' if not pointer else 'unavailable')
            records.append(record)
            if not pointer:
                continue
            try:
                prior = service.repository.get(db, 'runs', pointer['run_id'])
            except KeyError:
                continue
            assessment = next((a for a in prior.get('assessments', []) if a['id'] == pointer['assessment_id']), None)
            if (not assessment or assessment['requirement_id'] != requirement['id']
                    or assessment['revision'] != requirement['revision']
                    or pointer['revision'] != requirement['revision']
                    or pointer['source_version_ids'] != prior['input_version_ids']):
                continue
            source = assessment.get('source') or {}
            meanings = [business_review.join_source_meaning(m) for m in source.get('meanings', [])]
            representation = assessment.get('representation') or {}
            checks = [{k: c[k] for k in ('meaning_key', 'status', 'claim_ids', 'incorrect_claim_ids') if k in c}
                      for c in representation.get('checks', [])]
            ids = set(assessment.get('claim_ids', [])) | {cid for c in checks
                for key in ('claim_ids', 'incorrect_claim_ids') for cid in c.get(key, [])}
            linked = [c for c in prior.get('claims', []) if c['id'] in ids]
            claims = [business_run.compact_claim(c) for c in linked]
            options = prior['recipe']['options']
            related = business_review.related_blocks(prior, meanings, linked,
                chunks=autoschema.chunks(prior['blocks'], options['context_tokens'], options['review_tokens'], 1))
            for b in related:
                blocks[b['source_version_id'], b['id'], tuple(b.get('span', []))] = b
            record.update(status='provided', assessment_id=assessment['id'], run_id=prior['id'],
                meanings=meanings, representation_checks=checks,
                dependencies=representation.get('dependencies'), conjunctions=source.get('conjunctions'),
                meaning_conjunctions=source.get('meaning_conjunctions'), claims=claims,
                source_block_ids=list(dict.fromkeys(b['id'] for b in related)))
    return records, list(blocks.values())


def review_impacts(service, run, requirements, diff, versions, direct):
    dependencies, blocks = stored_dependencies(service, requirements)
    # Full receipts remain in the run. Reuse existing projections for repeated
    # source quotations and audit fields without dropping semantic uncertainty.
    changes = []
    for change in diff['changes']:
        value = dict(change)
        if 'source_corrections' in value:
            value['source_corrections'] = [{k: business_review.join_source_meaning(v) if k in {'before', 'after'} else v
                for k, v in c.items() if k in {'id', 'requirement_id', 'before', 'after', 'fields', 'mode', 'status'}}
                for c in value['source_corrections']]
        if 'changes' in value:
            value['changes'] = [{k: business_run.compact_claim(v) if v and k in {'before', 'after'} else v
                                for k, v in c.items()} for c in value['changes']]
        changes.append(value)
    result = business_run.json_call(service, run, 'change_impact',
        '원문 또는 근거 해석·후보 전후의 실제 변경과 각 업무 요구의 범위/조건을 대조한다. 기존 연결은 영향 후보이며 영향 확정이 아니다. '
        '기존 연결이 없어도 새 조건·예외·대상으로 관련되는 요구를 affected/new_relevance로 찾는다. '
        '각 요구를 빠짐없이 판정하고 실제 변경 id와 이유를 기록한다. 미변경 행/다른 대상은 유지한다. '
        'stored_dependencies의 실제 저장 의미·조건·후보·전제와 blocks를 변경 전후에 대조한다. '
        '저장 의미와 후보의 검수상태는 이전 판단이며 원문 지지의 정답이 아니다. '
        '정정의 소유 요구 ID가 다르다는 이유만으로 비영향으로 판정하지 않는다. '
        'unaffected에는 저장 의미와 변경의 독립성 또는 의미가 그대로 유지되는 구체 근거가 필요하다. '
        '저장 연결이 없는 unassessed는 비영향의 증거가 아니다. unavailable이나 미확정 전제는 독립성 증거가 아니다. '
        '자료없는 보행·수요·안전·인과 효과는 추정하지 않는다. 결정 불가하면 unknown이다.',
        dict(requirements=[{k: v for k, v in r.items() if k not in {'history', 'change_history', 'current_assessment'}} for r in requirements],
             direct_dependency_ids=direct, diff=dict(diff, changes=changes), versions=versions,
             stored_dependencies=dependencies, blocks=blocks,
             source_parents=[dict(block_id=b['id'], parent_block_ids=[p['id'] for p in autoschema.list_parents(b, blocks)])
                             for b in blocks if autoschema.list_parents(b, blocks)]), Impacts)
    valid = bool(result and len(result['items']) == len(requirements)
        and {r['requirement_id'] for r in result['items']} == {r['id'] for r in requirements})
    if valid and any(not set(r['change_ids']) <= {c['id'] for c in diff['changes']} for r in result['items']):
        valid = False
    if not valid:
        result = dict(items=[dict(requirement_id=r['id'], status='unknown', reason='불완전 변경 검수',
                                  change_ids=[], new_relevance=False) for r in requirements])
    unavailable = {d['requirement_id'] for d in dependencies if d['status'] == 'unavailable'}
    for impact in result['items']:
        if impact['requirement_id'] in unavailable:
            impact.update(status='unknown', reason='현재 평가 포인터에 일치하는 저장 의미·근거를 확인할 수 없음')
    return result, valid


def apply_impacts(service, run, requirements, impacts):
    """Share the same stale-assessment guard for source and interpretation changes."""
    with service.lock, service.repository.connect() as db:
        for impact in impacts:
            current = service.repository.get(db, 'requirements', impact['requirement_id'])
            before = next(r for r in requirements if r['id'] == current['id'])
            if (current['revision'] != before['revision']
                    or current.get('current_assessment') != before.get('current_assessment')):
                impact.update(status='unknown', reason='판정 중 요구 또는 현재 평가 변경')
            current.setdefault('change_history', []).append(dict(run_id=run['id'], impact=impact, recorded_at=utcnow()))
            if impact['status'] != 'unaffected':
                current['status'] = 'needs_review'
            service.repository.save(db, 'requirements', current)


def assessment_uses_version(snapshot, original, requirement_id, version_id):
    assessment = snapshot.get('assessments', {}).get(requirement_id)
    if not assessment:
        return True
    ids = set(assessment.get('claim_ids', [])) | {cid for check in
        (assessment.get('representation') or {}).get('checks', []) for cid in check.get('claim_ids', [])}
    claims = {c['id']: c for c in [*original.get('claims', []), *snapshot['claims']]}
    if not ids <= claims.keys():
        return True
    versions = {vid for cid in ids for vid in claims[cid]['source_version_ids']}
    refs = [ref for meaning in business_review.review_meanings(assessment.get('source') or {})
            for part in [meaning, *(meaning.get('field_judgments') or {}).values()]
            for ref in part.get('evidence', [])]
    try:
        versions.update(ref['source_version_id'] for ref in business_run.exact_evidence(
            refs, original.get('blocks', snapshot['blocks'])))
    except ValueError:
        return True
    return not versions or version_id in versions


def snapshot_invalidations(service, db, snapshot, original):
    """Use durable impact receipts even after a new assessment replaces needs_review."""
    invalidations, changes = {}, {}
    histories = sorted((history for row in db.execute('SELECT payload FROM requirements')
        for history in json.loads(row['payload']).get('change_history', [])), key=lambda h: h['recorded_at'])
    for history in histories:
        run_id = history['run_id']
        if run_id not in changes:
            changes[run_id] = service.repository.get(db, 'runs', run_id)
        change = changes[run_id]
        before = change.get('request', {}).get('before_version_id')
        if change.get('kind') != 'business_change' or before not in snapshot['source_versions']:
            continue
        pair = before, change['request']['after_version_id']
        # shortcut: exclude whole changed blocks until receipts identify independent unchanged claims.
        blocks = {bid for delta in change['diff']['changes'] for bid in
                  [delta.get('before_block_id'), *delta.get('before_block_ids', [])] if bid}
        event = invalidations.setdefault(pair, dict(event='business_source_change', snapshot_id=snapshot['id'],
            run_ids=[], reason='source_change_recorded_for_snapshot_version',
            claim_ids=[], block_ids=[], requirement_ids=[]))
        if run_id not in event['run_ids']:
            event['run_ids'].append(run_id)
        event['block_ids'] = sorted(set(event['block_ids']) | blocks)
        event['claim_ids'] = [c['id'] for c in snapshot['claims'] if any(
            e['source_version_id'] == before and e['block_id'] in event['block_ids'] for e in c.get('evidence', []))]
        impact = history['impact']
        event['requirement_ids'] = [rid for rid in event['requirement_ids'] if rid != impact['requirement_id']]
        if impact['status'] != 'unaffected' and assessment_uses_version(snapshot, original, impact['requirement_id'], before):
            event['requirement_ids'].append(impact['requirement_id'])
    return list(invalidations.values())


def analyze(service, request):
    started = monotonic()
    config = configuration()
    models = dict(draft=settings.STRUCTURING_MODEL, review=settings.KNOWLEDGE_REVIEW_MODEL)
    identity = ModelClient(config).identities(models, {r:49152 for r in models})
    with service.lock, service.repository.connect() as db:
        if service.closed or any(json.loads(r['payload'])['status'] in {'queued', 'running', 'cancel_requested'}
                                 for r in db.execute('SELECT payload FROM runs')):
            raise KnowledgeConflict('다른 실행이 종료된 뒤 변경 영향을 확인하세요.')
        versions = [service.repository.get(db, 'versions', identifier) for identifier in (request.before_version_id, request.after_version_id)]
        if versions[0]['source_id'] != versions[1]['source_id']:
            raise ValueError('같은 출처의 전후 버전이 필요합니다.')
        if any(v['processing_status'] != 'parsed' for v in versions):
            raise ValueError('전후 원문의 파싱이 필요합니다.')
        blocks = [service.parse_blocks(db, v['latest_parse_run_id'], v['id']) for v in versions]
        requirements = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM requirements')]
        if request.requirement_ids:
            if not set(request.requirement_ids) <= {r['id'] for r in requirements}:
                raise ValueError('알 수 없는 업무 요구')
            requirements = [r for r in requirements if r['id'] in request.requirement_ids]
        if not requirements:
            raise ValueError('영향을 확인할 업무 요구가 없습니다.')
        diff = differences(*blocks, request.key_fields)
        direct = []
        for requirement in requirements:
            current = requirement.get('current_assessment')
            if current and request.before_version_id in current['source_version_ids']:
                direct.append(requirement['id'])
        recipe = dict(generation=config, models=models, options=dict(review_tokens=4096, extraction_tokens=4096,
                     concept_tokens=512, context_tokens=49152, timeout=1800, think=False))
        run = dict(id=uuid4().hex, kind='business_change', status='running', units=[], input_version_ids=[v['id'] for v in versions],
                   recipe=recipe, started_at=utcnow(), finished_at=None, metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0),
                   diff=diff, direct_dependency_ids=direct, requirements=requirements, request=request.model_dump(),
                   model_identity=identity)
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    # ponytail: inspect all selected requirements, including unlinked ones. Add a
    # measured candidate index only when the requirement inventory outgrows this.
    result, valid = review_impacts(service, run, requirements, diff, versions, direct)
    apply_impacts(service, run, requirements, result['items'])
    with service.lock, service.repository.connect() as db:
        run.update(status='cancelled' if run['status'] == 'cancel_requested' else 'succeeded' if valid else 'partial', impacts=result['items'], finished_at=utcnow())
        run['metrics']['elapsed_s'] = monotonic() - started
        service.repository.save(db, 'runs', run)
    return run
