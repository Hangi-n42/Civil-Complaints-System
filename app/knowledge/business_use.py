"""Review source claims without turning search concepts into approved ontology types."""
from copy import deepcopy
import json
import re
from time import monotonic
from uuid import uuid4
from typing import Literal

from pydantic import BaseModel, Field, create_model, field_validator

from . import business_run, business_review
from .service import KnowledgeConflict, encode, utcnow

ELIGIBILITY_CONTRACT = 'current-claim-local-dependencies-v8-applicability'
ANSWER_CONTRACT = 'provided-unique-citations-nonempty-answer-v2'


def restricted_sources(db, version_ids):
    from .snapshots import _statuses
    statuses = _statuses(db)
    return [dict(source_version_id=v, state=statuses['source_version', v]['state']) for v in version_ids
            if statuses.get(('source_version', v), {}).get('state', 'allowed') != 'allowed']


def eligibility(run):
    eligible, blocked, preserved_current = set(), {}, set()
    requires_whole_check, whole_supported = set(), set()
    latest = {a['requirement_id']: a for a in run['assessments']}
    requirements = {r['id']: r for r in run['requirements']}
    changed_existing = {v['before']['id'] for repair in [*run.get('prior_repairs', []), *run['repairs']]
                        for v in repair['changes'] if v['before']}
    def exclude(ids, reason):
        for cid in ids:
            blocked.setdefault(cid, []).append(reason)
    for assessment in latest.values():
        representation = assessment.get('representation') or {}
        checks = representation.get('checks', [])
        inspected = {cid for check in checks for cid in check['claim_ids']}
        if assessment.get('input_fingerprint') != business_run.assessment_fingerprint(
                run, requirements[assessment['requirement_id']], assessment['source'], assessment.get('review_scope')):
            exclude(inspected, 'stale_assessment')
            continue
        meanings = {m['key']: m for m in (assessment.get('source') or {}).get('meanings', [])}
        for check in checks:
            meaning = meanings.get(check['meaning_key'], {})
            if business_review.separated(run):
                requires_whole_check.update(check['claim_ids'])
                exclude({cid for cid, state in check.get('claim_support', {}).items() if state == 'unknown'},
                        'unresolved_claim_support')
                exclude({cid for cid, state in check.get('claim_support', {}).items() if state == 'incorrect'},
                        'confirmed_expression_error')
            exclude(check.get('incorrect_claim_ids', []), 'confirmed_expression_error')
            if check['status'] == 'incorrect' or meaning.get('source_status') == 'refuted':
                exclude(check['claim_ids'], 'confirmed_error_or_refutation')
            elif check['status'] == 'unknown' or meaning.get('source_status') == 'unknown':
                exclude(check['claim_ids'], 'unresolved_meaning_not_false')
        preserved = {p['target_id'] for p in representation.get('preservation_checks', [])
                     if p['status'] == 'preserved' and p['before_normal_meanings'] and p['after_locations']}
        preserved_current.update(preserved)
        exclude({p['target_id'] for p in representation.get('preservation_checks', [])
                 if p['target_id'] not in preserved}, 'normal_meaning_preservation_conflict')
        # Incomplete source judgments cannot approve claims. They do not veto
        # an independent valid judgment unless a claim-specific problem above exists.
        blocked_keys, global_blocks = business_review.blocked(assessment, include_global=False)
        if business_review.current(run):
            exclude({cid for c in checks if c['meaning_key'] in blocked_keys for cid in c['claim_ids']}, 'meaning_dependency_blocked')
            if global_blocks or not assessment['representation']:
                continue  # Global incompleteness gives no approval; scoped faults still veto above.
        else:
            if assessment['errors'] or not assessment['representation'] or assessment['representation']['source_challenges']:
                continue
            blocked_keys = set()
        nonessential = {c['meaning_key'] for c in representation.get('source_checks', [])
                        if not c['required_for_requirement']}
        supported = {m['key'] for m in assessment['source']['meanings'] if m['key'] not in nonessential | blocked_keys and m['source_status'] == 'supported'
                     and m['availability'] == 'provided' and m['evidence'] and not m.get('record_error')}
        if business_review.separated(run):
            whole_supported.update(cid for check in checks if check['meaning_key'] in supported
                                   for cid, state in check.get('claim_support', {}).items() if state == 'supported')
        for check in assessment['representation']['checks']:
            if check['meaning_key'] in supported and check['status'] == 'represented':
                eligible.update(check['claim_ids'])
    exclude(changed_existing - preserved_current, 'normal_meaning_preservation_unconfirmed')
    exclude(requires_whole_check - whole_supported, 'whole_claim_support_unconfirmed')
    return eligible - set(blocked) - {c['id'] for c in run['claims'] if c.get('extraction_error') or c.get('superseded_by')}, blocked


def review_eligibility(change, run):
    eligible, blocked = eligibility(run)
    for cid in change.get('invalidated_claim_ids', []):
        eligible.discard(cid)
        blocked.setdefault(cid, []).append('corrected_in_new_run')
    current = {c['id']: c for c in run['claims']}
    unchanged = {c['id'] for c in change['candidates'] if c == current.get(c['id'])}
    for cid in {c['id'] for c in change['candidates']} - unchanged:
        blocked.setdefault(cid, []).append('candidate_changed_since_publication')
    return eligible & unchanged, blocked


def publish(service, run):
    eligible, blocked = eligibility(run)
    latest = {a['requirement_id']: a for a in run['assessments']}
    change = dict(id=uuid4().hex, kind='source_graph', revision=0, run_id=run['id'], created_at=utcnow(),
                  candidates=deepcopy(run['claims']), eligibility_blocks=blocked, eligible_ids=sorted(eligible), decisions=[],
                  eligibility_contract=ELIGIBILITY_CONTRACT,
                  completion_contract=business_run.COMPLETION_CONTRACT,
                  requirement_assessment_ids={r: a['id'] for r, a in latest.items()},
                  promotion_status='source_claim_review; has_concept_is_not_approved_is_a')
    with service.lock, service.repository.connect() as db:
        db.execute('INSERT INTO changesets VALUES(?,?)', (change['id'], encode(change)))
    return change


def explicit_correction_options(run):
    """A reviewer may confirm only the exact jointly corrected text, separately from model review."""
    latest = {a['requirement_id']: a for a in run['assessments']}
    choices = []
    for correction in run.get('source_corrections', []):
        if correction['mode'] != 'replace' or correction['error_owner'] != 'both':
            continue
        assessment = latest.get(correction['requirement_id'], {})
        meaning = next((m for m in (assessment.get('source') or {}).get('meanings', [])
            if m['key'] == correction['before']['key'] and (m.get('correction') or {}).get('id') == correction['id']), None)
        if not meaning or correction['source_versions'] != run['input_version_ids'] or correction['requirement_revision'] != assessment.get('revision'):
            continue
        receipts = [r for r in [*run.get('prior_repairs', []), *run['repairs']] if r['id'] == correction['edit_id']]
        ids = [c['id'] for receipt in receipts for edit in receipt['changes'] for c in run['claims']
            if c == edit['after'] and c.get('raw', {}).get('Event') == meaning['statement'] and not c.get('superseded_by')]
        if ids:
            choices.append(dict(correction_id=correction['id'], claim_ids=ids, requirement_id=correction['requirement_id'],
                assessment_id=assessment.get('id'), meaning=deepcopy(meaning), basis='explicit_reviewer_not_model_validation'))
    return choices


def change_view(service, changeset_id):
    with service.repository.connect() as db:
        change = service.repository.get(db, 'changesets', changeset_id)
        if change.get('kind') != 'source_graph':
            raise ValueError('업무 지식 변경안이 아닙니다.')
        run = service.repository.get(db, 'runs', change['run_id'])
    eligible, blocked = review_eligibility(change, run)
    return dict(change, eligible_ids=sorted(eligible), published_eligible_ids=change['eligible_ids'],
                explicit_review_options=[o for o in explicit_correction_options(run)
                    if not set(o['claim_ids']).intersection(change.get('invalidated_claim_ids', []))],
                candidate_versions={c['id']: business_run.autoschema.identifier('claim', c) for c in change['candidates']},
                source_meanings=[dict(requirement_id=rid, meaning=deepcopy(m),
                    version=business_run.autoschema.identifier('meaning', m))
                    for rid, a in {a['requirement_id']: a for a in run['assessments']}.items()
                    for m in (a.get('source') or {}).get('meanings', [])],
                completion_contract=business_run.COMPLETION_CONTRACT,
                published_completion_contract=change.get('completion_contract'),
                published_eligibility_contract=change.get('eligibility_contract', 'current-claim-all-requirements-v1'),
                eligibility_blocks=blocked, eligibility_contract=ELIGIBILITY_CONTRACT)


def decide(service, changeset_id, request):
    with service.lock, service.repository.connect() as db:
        change = service.repository.get(db, 'changesets', changeset_id)
        if change['kind'] != 'source_graph' or change['revision'] != request.expected_revision:
            raise KnowledgeConflict('검토 변경안의 종류/버전이 다릅니다.')
        run = service.repository.get(db, 'runs', change['run_id'])
        eligible, _ = review_eligibility(change, run)
        explicit = [o for o in explicit_correction_options(run) if o['correction_id'] in request.confirm_source_correction_ids
                    and not set(o['claim_ids']).intersection(change.get('invalidated_claim_ids', []))]
        if {o['correction_id'] for o in explicit} != set(request.confirm_source_correction_ids) or any(
                not set(o['claim_ids']) <= set(request.accept_ids) for o in explicit):
            raise ValueError('현재 정정본의 후보를 선택하고 정정 해석 확인을 명시해야 합니다.')
        if not set(request.accept_ids) <= eligible | {cid for o in explicit for cid in o['claim_ids']}:
            raise ValueError('근거·표현 검수에서 확인되지 않은 후보는 승인할 수 없습니다.')
        if restricted_sources(db, run['input_version_ids']):
            raise KnowledgeConflict('사용이 제한된 원문 버전의 후보는 승인할 수 없습니다.')
        for requirement in run['requirements']:
            current = service.repository.get(db, 'requirements', requirement['id'])
            if current['revision'] != requirement['revision'] or current['status'] == 'needs_review':
                raise KnowledgeConflict('요구 또는 관련 원문 변경 이후 재검수가 필요합니다.')
        selected = [dict(c, review_status='accepted') for c in change['candidates'] if c['id'] in request.accept_ids]
        decision = dict(id=uuid4().hex, kind='source_graph', changeset_id=change['id'], actor=request.actor,
                        completion_contract=business_run.COMPLETION_CONTRACT,
                        eligibility_contract=ELIGIBILITY_CONTRACT, eligible_ids_at_review=sorted(eligible),
                        reason=request.reason, accepted_ids=request.accept_ids, created_at=utcnow())
        decision['explicit_meaning_reviews'] = deepcopy(explicit)
        change['decisions'].append(decision['id'])
        change['revision'] += 1
        service.repository.save(db, 'changesets', change)
        db.execute('INSERT INTO decisions VALUES(?,?)', (decision['id'], encode(decision)))
        latest = {a['requirement_id']: deepcopy(a) for a in run['assessments']}
        for assessment in latest.values():
            assessment.update(recorded_status=assessment['status'],
                recorded_completion_contract=assessment.get('completion_contract'))
            assessment.update(business_run.requirement_completion(assessment, request.accept_ids))
        snapshot = dict(id=uuid4().hex, kind='source_graph', parent_id=None, run_id=run['id'],
                        completion_contract=business_run.COMPLETION_CONTRACT,
                        eligibility_contract=ELIGIBILITY_CONTRACT,
                        created_at=utcnow(), actor=request.actor, reason=request.reason,
                        counts=dict(claims=len(selected), requirements=len(latest)), claims=selected,
                        concepts=deepcopy(run['concepts']), requirements=deepcopy(run['requirements']),
                        assessments=latest, source_versions=deepcopy(run['sources']),
                        blocks=deepcopy(run['blocks']), assertions={}, entity_links={},
                        ontology_version_id=None, activation='explicit_query_only')
        snapshot['explicit_meaning_reviews'] = deepcopy(explicit)
        direct = business_review.current_candidate_reviews(run)
        snapshot['reviewed_claim_evidence'] = {
            c['id']: dict(claim_version=business_run.autoschema.identifier('claim', c),
                receipt_id=direct[c['id']]['receipt_id'], unit_id=direct[c['id']]['unit_id'],
                evidence=deepcopy(direct[c['id']]['check']['evidence']))
            for c in selected if c['id'] in direct
            and direct[c['id']]['check']['claim_support'].get(c['id']) == 'supported'}
        db.execute('INSERT INTO snapshots VALUES(?,?)', (snapshot['id'], encode(snapshot)))
        db.execute('INSERT INTO snapshot_events VALUES(?,?)', (decision['id'], encode(dict(
            decision, event='reviewed_source_graph_snapshot', snapshot_id=snapshot['id']))))
    return dict(decision=decision, snapshot_id=snapshot['id'], changeset_revision=change['revision'])


def snapshots(service):
    with service.repository.connect() as db:
        return dict(items=[s for row in db.execute('SELECT payload FROM snapshots ORDER BY rowid DESC')
                          if (s := json.loads(row['payload'])).get('kind') == 'source_graph'])


class Answer(BaseModel):
    answer: str = Field(min_length=1)
    choice: Literal['A', 'B', 'C', 'D'] | None
    citations: list[str]
    limitations: list[str]

    @field_validator('answer')
    @classmethod
    def nonempty_answer(cls, value):
        if not value.strip():
            raise ValueError('빈 답변은 완료된 답변이 아닙니다.')
        return value

    @field_validator('citations')
    @classmethod
    def unique_citations(cls, values):
        if len(values) != len(set(values)):
            raise ValueError('같은 근거 ID를 중복 인용할 수 없습니다.')
        return values


class SourceAnswer(Answer):
    @field_validator('citations', mode='before')
    @classmethod
    def deduplicate_citations(cls, values):
        # Lossless formatting repair; supplied-ID validation still runs afterward.
        if isinstance(values, list) and all(isinstance(v, str) for v in values):
            return list(dict.fromkeys(values))
        return values


def concept_hints(snapshot):
    """Candidate concepts help retrieval only; they never become answer evidence."""
    hints = {c['id']: [] for c in snapshot['claims']}
    for concept in snapshot.get('concepts', []):
        if concept['status'] not in {'unreviewed', 'accepted'}:
            continue
        for cid in concept['target'].get('claim_ids', []):
            if cid in hints:
                hints[cid].extend(concept['concepts'])
    return {cid: list(dict.fromkeys(values)) for cid, values in hints.items()}


def reviewed_answer_meanings(snapshot, selected, requirement_ids):
    """Carry existing review scope and literal evidence, not a new truth judgment."""
    rows = []
    explicit = {(e['requirement_id'], e['meaning']['key']): e for e in snapshot.get('explicit_meaning_reviews', [])}
    for rid, assessment in snapshot.get('assessments', {}).items():
        if requirement_ids and rid not in requirement_ids:
            continue
        checks = {c['meaning_key']: c for c in (assessment.get('representation') or {}).get('checks', [])}
        for meaning in (assessment.get('source') or {}).get('meanings', []):
            check = checks.get(meaning['key'], {})
            confirmation = explicit.get((rid, meaning['key']))
            if confirmation:
                meaning = confirmation['meaning']
                check = dict(status='explicitly_reviewed', claim_ids=confirmation['claim_ids'],
                    claim_support={cid:'explicitly_reviewed' for cid in confirmation['claim_ids']})
            ids = sorted(selected.intersection(check.get('claim_ids', [])))
            if not ids:
                continue
            row = dict(requirement_id=rid, assessment_id=assessment['id'],
                claim_ids=ids, expression_status=check['status'], **{k: deepcopy(meaning.get(k)) for k in
                ('key', 'statement', 'conditions', 'exceptions', 'period', 'references', 'source_status',
                 'availability', 'record_error', 'requirement_link')},
                field_judgments=deepcopy(meaning.get('field_judgments', {})))
            row['field_checks'] = business_review.source_judgment(meaning)['field_checks']
            row['claim_support'] = {cid: check.get('claim_support', {}).get(cid, 'not_assessed') for cid in ids}
            row.update(required_claim_ids=deepcopy(check.get('claim_ids', [])),
                complete_claim_bundle=set(check.get('claim_ids', [])) <= selected,
                premise_keys=meaning.get('premise_keys'),
                interpretation_version=business_run.autoschema.identifier('meaning', meaning),
                judgment_origin=deepcopy(meaning.get('correction', {'origin': 'model'})))
            try:
                row['evidence'] = business_run.exact_evidence(meaning['evidence'], snapshot['blocks'])
            except ValueError as exc:
                row.update(evidence=[], record_error=str(exc))
            rows.append(row)
    return rows


def public_answer_requirements(requirements):
    return [{k: r.get(k, '') for k in ('id', 'question', 'criterion', 'target', 'situation', 'period')}
            for r in requirements]


def bind_answer_items(request, requirements):
    """Bind the public plan to this execution without revising or approving requirements."""
    by_id = {r['id']: r for r in requirements if r['id'] in request.requirement_ids}
    items = [i.model_dump() for i in request.answer_items]
    for item in items:
        requirement = by_id.get(item['requirement_id'])
        if not requirement or item['requirement_revision'] != requirement['revision']:
            raise ValueError('공개 답변 항목의 요구 ID/revision이 선택한 요구와 다릅니다.')
        if item['request_quote'] not in requirement[item['field']]:
            raise ValueError('공개 답변 항목은 원래 question/criterion의 정확한 구절이어야 합니다.')
    return items


def exact_row_answer_fields(snapshot, selected, requirement_ids):
    """Expose accepted literal cells, not new model-reviewed propositions."""
    rows = []
    for rid, assessment in snapshot['assessments'].items():
        if rid not in requirement_ids:
            continue
        checks = {c['meaning_key']: c for c in (assessment.get('representation') or {}).get('checks', [])}
        for claim in snapshot['claims']:
            if claim['id'] not in selected or claim.get('review_status') != 'accepted':
                continue
            ref = business_run.exact_direct_row(claim, snapshot['blocks'])
            if not ref or ref['source_version_id'] not in snapshot['source_versions']:
                continue
            linked = [m for m in (assessment.get('source') or {}).get('meanings', [])
                if checks.get(m['key'], {}).get('status') == 'represented'
                and claim['id'] in checks[m['key']]['claim_ids']
                and checks[m['key']].get('claim_support', {}).get(claim['id']) == 'supported'
                and m['source_status'] == 'supported' and m['availability'] == 'provided'
                and not m.get('record_error') and any(e['block_id'] == ref['block_id']
                    and e.get('source_version_id') == ref['source_version_id'] for e in m['evidence'])]
            if not linked:
                continue
            block = business_run.exact_tabular_block(ref, snapshot['blocks'])
            version = snapshot['source_versions'][ref['source_version_id']]
            for field, value in claim['raw']['fields'].items():
                rows.append(dict(kind='exact_row_field', requirement_id=rid,
                    key=f"field:{claim['id']}:{field}", field_name=field, field_value=deepcopy(value),
                    statement=field + ': ' + encode(value), required_claim_ids=[claim['id']], premise_keys=[],
                    row_fields=deepcopy(claim['raw']['fields']), evidence=[deepcopy(ref)],
                    source_version_id=ref['source_version_id'], source_filename=version.get('filename', ''),
                    source_dates=deepcopy(version.get('dates', [])),
                    row_locator={k:v for k,v in block['locator'].items() if k != 'fields'},
                    judgment_origin=dict(origin='exact_source_row_match', semantic_review=False)))
    return rows


def unresolved_finding_notes(source):
    """Consume validated resolution states without rewriting findings or judging their reasons."""
    states = {}
    for row in source.get('finding_resolutions', []):
        states.setdefault(row['finding_id'], []).append(row['status'])
    return [f['text'] for f in source.get('findings', [])
            if states.get(f['id']) not in (['resolved'], ['not_required'])]


def reviewed_item_answer(service, run, request, requirements):
    """Select complete reviewed propositions; the server renders their unchanged content."""
    available = {}
    excluded = []
    for meaning in run['reviewed_meanings']:
        explicit = meaning['expression_status'] == 'explicitly_reviewed'
        valid = (meaning['complete_claim_bundle'] and meaning['expression_status'] in {'represented', 'explicitly_reviewed'}
            and meaning['source_status'] == 'supported' and meaning['availability'] == 'provided'
            and not business_review.unresolved_source_fields(meaning)
            and meaning['evidence'] and not meaning['record_error']
            and all(meaning['claim_support'].get(cid) == ('explicitly_reviewed' if explicit else 'supported') for cid in meaning['required_claim_ids']))
        if valid:
            available[f'm{len(available)+1}'] = meaning
        else:
            excluded.append(dict(key=meaning['key'], requirement_id=meaning['requirement_id'],
                reason='incomplete_current_approved_bundle_or_review'))
    # Missing premise edges are unknown, not proof of independence. Known AND
    # premises must also be provided before a compound meaning can be selected.
    while True:
        keys = {(m['requirement_id'], m['key']) for m in available.values()}
        missing = [ref for ref, m in available.items() if any(
            (m['requirement_id'], key) not in keys for key in m.get('premise_keys') or [])]
        if not missing:
            break
        for ref in missing:
            m = available.pop(ref)
            excluded.append(dict(key=m['key'], requirement_id=m['requirement_id'], reason='missing_required_premise'))
    for field in run.get('exact_row_answer_fields', []):
        available[f'f{len(available)+1}'] = field
    # Applicability belongs to the prior request. Select afresh for these bound
    # public items, including when the prior request's applicability was unknown.
    run['answer_meaning_selection'] = dict(available=deepcopy(available), excluded=excluded,
                                         public_answer_items=deepcopy(run['answer_items']))
    if not available:
        return dict(answer='확인된 후보·조건·전제가 함께 제공된 의미가 없습니다.', citations=[], choice=None,
                    limitations=['현재 검토 버전의 표현 연결을 확인해야 합니다.'])
    selection = create_model('ReviewedSelection', meaning_ref=(Literal[tuple(available)], Field(...)),
        use=(Literal['direct_fact', 'premise_only'], Field(...)))
    row = create_model('ReviewedItemSelection', item_id=(Literal[tuple(i['id'] for i in run['answer_items'])], Field(...)),
        selected=(list[selection], Field(...)),
        unconfirmed=(list[str], Field(description='Concrete requested fact or inference link not established; never an affirmative conclusion.')))
    output_type = create_model('ReviewedItemSelections', items=(list[row], Field(...)))
    payload, row_contexts = {}, {}
    row_keys = ('row_fields', 'evidence', 'source_version_id', 'source_filename', 'source_dates', 'row_locator')
    for ref, meaning in available.items():
        value = {k:v for k,v in meaning.items() if k not in {'requirement_link', 'requirement_applications'}}
        if meaning.get('kind') == 'exact_row_field':
            cid = meaning['required_claim_ids'][0]
            row_contexts[cid] = {k:meaning[k] for k in row_keys}
            value = {k:v for k,v in value.items() if k not in row_keys}
            value['row_context_id'] = cid
        payload[ref] = value
    # Literal column names only; this does not infer unnamed fields from a question.
    requested_fields = {item['id']: [name for name in dict.fromkeys(
        m['field_name'] for m in available.values() if m.get('kind') == 'exact_row_field'
        and m['requirement_id'] == item['requirement_id']) if re.search(
            r'(?<![A-Za-z0-9_])' + r'\s*'.join(map(re.escape, re.sub(r'\s+', '', name))) + r'(?![A-Za-z0-9_])',
            item['request_quote'], re.IGNORECASE)] for item in run['answer_items']}
    output = business_run.json_call(service, run, 'business_qa',
        '공개 질문/criterion의 항목별로 해당하는 검토 의미 ID만 선택한다. 문장·결론을 새로 작성하지 않는다. '
        '각 의미의 출처/조건/대상/기간과 질문 적용성을 대조한다. 직접 답인 사실은 direct_fact, '
        '결론에 추가 연결이 필요하면 premise_only로 고르고 그 구체 미확인 연결을 unconfirmed에 쓴다. '
        '명시적 사실·조건을 새로운 허용·의무·보장으로 확대하지 않는다. 일부 적용 범위를 일반화하지 않는다. '
        '모든 공개 항목에 유용한 의미 또는 구체 공백이 필요하다. 불필요한 의미는 선택하지 않는다. '
        '검토 의미도 오류 가능하며 judgment_origin은 정답 보장이 아니다. 원문과 모순이면 선택하지 말고 공백에 이유를 남긴다.' + (
        ' kind=exact_row_field는 승인된 후보와 원문 행이 일치하는 직접 셀값이며 새 의미 검수 결과가 아니다. '
        'row_context_id의 row_contexts에 원문 행·출처 문맥이 있다. 질문/공개 항목이 요청한 필드만 선택하고 비요청 필드는 나열하지 않는다. '
        '열 이름과 자연어가 섞인 요청도 각 요청 사실에 해당하는 필드를 빠짐없이 대조한다. '
        '파일 기준일은 현실 최신성이나 전체 요구 충족의 증거가 아니며 assessment_limitations를 유지한다.'
        if run.get('exact_row_answer_fields') else ''),
        dict(question=request.question, public_requirements=requirements, public_answer_items=run['answer_items'],
             requested_row_fields=requested_fields,
             **(dict(row_contexts=row_contexts) if row_contexts else {}),
             **(dict(assessment_limitations=run['answer_assessment_limitations'])
                if run.get('answer_assessment_limitations') else {}),
             # Earlier whole-requirement applicability is not a verdict on the current public item.
             reviewed_meanings=payload), output_type)
    if output is None:
        return None
    run['answer_meaning_selection']['output'] = deepcopy(output)
    rendered, citations, limitations, errors = [], [], [], []
    for item in run['answer_items']:
        matches = [r for r in output['items'] if r['item_id'] == item['id']]
        if len(matches) != 1:
            errors.append(item['id'] + ': selection_missing_or_duplicate')
            rendered.append(item['request_quote'] + '\n응답 기록 미완성')
            continue
        row = matches[0]
        lines = [item['request_quote']]
        shown_rows, selected_fields = set(), set()
        for selected in row['selected']:
            m = available[selected['meaning_ref']]
            if m['requirement_id'] != item['requirement_id']:
                errors.append(item['id'] + ': wrong_requirement'); continue
            if m.get('kind') == 'exact_row_field':
                selected_fields.add(m['field_name'])
                lines.append(('원문 행 값 (결론 연결 미확인): ' if selected['use'] == 'premise_only'
                              else '원문 행 값: ') + m['statement'])
                if selected['use'] == 'premise_only' and not row['unconfirmed']:
                    errors.append(item['id'] + ': inference_link_not_specified')
                citations.extend(m['required_claim_ids'])
                row_id = m['required_claim_ids'][0]
                if row_id not in shown_rows:
                    shown_rows.add(row_id)
                    locator = m['row_locator']
                    position = (locator['json_pointer'] if 'json_pointer' in locator else
                        str(locator.get('sheet', '')) + ' ' + str(locator.get('physical_row', '')) + '행')
                    lines.append('자료: ' + m['source_filename'] + '; 원문 행 위치: ' + position)
                    if m['source_dates']:
                        lines.append('자료에 기록된 날짜: ' + ', '.join(d['value'] for d in m['source_dates']))
                continue
            prefix = '확인된 전제 (결론 연결 미확인): ' if selected['use'] == 'premise_only' else '검토된 원문 의미: '
            lines.append(prefix + m['statement'])
            for field, label in [('conditions', '조건'), ('exceptions', '예외'), ('period', '기간'), ('references', '참조')]:
                value = m.get(field)
                status = (m.get('field_checks') or business_review.source_judgment(m)['field_checks'])[field]
                # Preserve every legacy qualifier in its whole-meaning bundle;
                # do not invent a separate field verdict or silently broaden it.
                if value and status in {'supported', 'not_assessed'}:
                    lines.append(label + ': ' + (' / '.join(value) if isinstance(value, list) else value))
            citations.extend(m['required_claim_ids'])
            if m.get('premise_keys') is None:
                limitations.append(m['key'] + ': 추가 연결 전제의 독립성은 확인되지 않았습니다.')
            if selected['use'] == 'premise_only' and not row['unconfirmed']:
                errors.append(item['id'] + ': inference_link_not_specified')
        for gap in row['unconfirmed']:
            lines.append('확인 불가: ' + gap)
            limitations.append(gap)
        if not row['selected'] and not row['unconfirmed']:
            errors.append(item['id'] + ': empty_item')
        for name in requested_fields[item['id']]:
            if name not in selected_fields:
                errors.append(item['id'] + ': requested_row_field_not_selected:' + name)
                gap = '요청한 필드가 답변 근거 선택에서 빠졌습니다: ' + name
                lines.append(gap)
                limitations.append(gap)
        rendered.append('\n'.join(lines))
    for limitation in run.get('answer_assessment_limitations', []):
        text = ('요청한 내용의 전체 충족은 아직 확인되지 않았습니다'
            + (' (기준 시점: ' + limitation['period'] + ')' if limitation['period'] else '') + '. '
            + '제공된 파일의 행값과 날짜는 이 미확정을 해소하지 않습니다.')
        rendered.append(text)
        limitations.append(text)
        for note in dict.fromkeys([*limitation['gaps'], *limitation.get('review_notes', [])]):
            text = '기존 검수의 미확정 관련 기록 (확정 사실 아님): ' + note
            rendered.append(text)
            limitations.append(text)
    run['answer_item_errors'] = errors
    return dict(answer='\n\n'.join(rendered), citations=list(dict.fromkeys(citations)), choice=None,
                limitations=list(dict.fromkeys(limitations)))


def item_answer(service, run, request, source_evidence, source_versions, reference_map, requirements):
    """One semantic answer per frozen public item; no second whole-answer rewrite."""
    evidence = {f't{i + 1}': row for i, row in enumerate(source_evidence)}
    if not evidence:
        return None
    quote = create_model('AnswerSupport', evidence_ref=(Literal[tuple(evidence)], Field(...)),
                         quote=(str, Field(min_length=1)))
    claim = create_model('ItemConclusion', statement=(str, Field(min_length=1)),
        kind=(Literal['direct', 'inference', 'conditional_duty', 'exclusion'], Field(...)),
        conditions=(list[str], Field(...)), exceptions=(list[str], Field(...)),
        support=(list[quote], Field(min_length=1)),
        reasoning=(str, Field(description='For inference: premises and derivation; otherwise empty.')))
    row = create_model('PublicItemAnswer', item_id=(Literal[tuple(i['id'] for i in run['answer_items'])], Field(...)),
        conclusions=(list[claim], Field(...)),
        missing=(list[str], Field(description='Specific requested facts not established by these sources, with the reason; empty only if fully answered.')))
    response_type = create_model('PublicItemAnswers', items=(list[row], Field(...)),
                                 choice=(Literal['A', 'B', 'C', 'D'] | None, None))
    output = business_run.json_call(service, run, 'business_qa',
        '고정된 public_answer_items 각각에 대해 질문에 유용한 설명·비교 결론을 한국어로 작성한다. '
        '요청 항목별로 원문이 지지하는 결론을 나누고 주체·조건·예외·기간·기산점·단위를 유지한다. '
        '원문 목록을 반복하거나 모든 항목을 미확인으로 회피하지 않는다. application 문맥은 새 요청을 만들지 않는다. '
        'support에는 실제 원문 주소와 정확한 인용을 넣는다. 주체/조건/예외가 다른 구간에 있으면 함께 인용한다. '
        'direct는 원문이 직접 진술한 효과만 쓴다. 조건부 의무는 conditional_duty와 conditions, 제외는 exclusion으로 적는다. '
        '추론은 inference로 분리하고 reasoning에 원문 전제와 결론 사이의 논증을 쓴다. 추론을 명시적 허용으로 바꾸지 않는다. '
        '기간·처리 사실·담당 업무·허용·의무는 서로 다른 명제다. 한 명제의 원문만으로 다른 명제의 법적 효과를 확정하지 않는다. '
        '조건부 문장의 의무나 예외를 그 조건 밖에 확장하지 않는다. 원문이 다른 업무를 제외하지 않았다는 사실만으로 허용을 확정하지 않는다. '
        '각 항목은 conclusions 또는 구체적인 missing이 있어야 한다. 일부 확인이면 확인된 결론도 쓰고 남은 요청 사실과 부족한 근거를 missing에 특정한다. '
        '출처 부족과 답변 누락을 구별한다. 참고 사실이 있어도 요청한 효과를 확인하지 못하면 그 차이를 밝힌다. '
        '최종 전체 답변은 서버가 조립하므로 별도 종합 결론을 쓰지 않는다. choice는 선택지가 있을 때만 고른다.',
        dict(question=request.question, choices=request.choices, public_answer_items=run['answer_items'],
             public_requirements=public_answer_requirements(requirements), source_versions=source_versions,
             source_evidence=[dict(reference=ref, **value) for ref, value in evidence.items()]),
        response_type, reference_map=reference_map)
    run['answer_contract'] = 'public-items-source-conclusions-server-assembly-experimental-v1'
    run['answer_selection'] = deepcopy(output)
    errors, restored = {}, {}
    for item in (output or {}).get('items', []):
        key = item['item_id']
        if key in restored:
            errors.setdefault(key, []).append('duplicate_item')
        restored[key] = deepcopy(item)
        if not item['conclusions'] and not any(m.strip() for m in item['missing']):
            errors.setdefault(key, []).append('empty_item')
        valid = []
        for index, conclusion in enumerate(restored[key]['conclusions']):
            faults = []
            if conclusion['kind'] == 'inference' and not conclusion['reasoning'].strip():
                faults.append('inference_without_reason')
            if conclusion['kind'] == 'conditional_duty' and not conclusion['conditions']:
                faults.append('duty_without_condition')
            for support in conclusion['support']:
                source = evidence.get(support['evidence_ref'])
                if not source or not support['quote'].strip() or support['quote'] not in source['text']:
                    faults.append('invalid_source_quote')
                    continue
                start = source['span'][0] + source['text'].index(support['quote'])
                support['source'] = dict(block_id=source['id'], source_version_id=source['source_version_id'],
                    parse_run_id=source['parse_run_id'], span=[start, start + len(support['quote'])])
            errors.setdefault(key, []).extend(f'{fault}:{index}' for fault in faults)
            if not faults:
                valid.append(conclusion)
        restored[key]['conclusions'] = valid
    expected = {i['id'] for i in run['answer_items']}
    for key in restored.keys() - expected:
        errors.setdefault(key, []).append('unexpected_item')
    for key in expected:
        if key not in restored:
            errors.setdefault(key, []).append('missing_item')
            restored[key] = dict(item_id=key, conclusions=[], missing=[])
        if 'duplicate_item' in errors.get(key, []):
            restored[key].update(conclusions=[], missing=[])
        restored[key]['record_errors'] = errors.get(key, [])
    run['answer_item_errors'] = [dict(item_id=k, errors=v) for k, v in errors.items() if v]
    lines, citations, limitations = [], [], []
    labels = dict(direct='원문 확인', inference='근거에 따른 추론', conditional_duty='조건부 의무', exclusion='제외 업무')
    for public in run['answer_items']:
        item = restored[public['id']]
        lines.append(public['request_quote'])
        if item['record_errors']:
            lines.append('- 응답 기록 미완성: ' + ', '.join(item['record_errors']))
        for conclusion in item['conclusions']:
            lines.append(f"- [{labels[conclusion['kind']]}] {conclusion['statement']}")
            for field, label in [('conditions', '조건'), ('exceptions', '예외')]:
                if conclusion[field]:
                    lines.append('  ' + label + ': ' + '; '.join(conclusion[field]))
            if conclusion['reasoning']:
                lines.append('  추론 근거: ' + conclusion['reasoning'])
            citations.extend(cid for s in conclusion['support'] for link in evidence[s['evidence_ref']]['claim_references']
                             for cid in link['claim_ids'])
        for missing in item['missing']:
            limitation = public['request_quote'] + ' — 확인 불가: ' + missing
            lines.append('- ' + limitation)
            limitations.append(limitation)
    return dict(answer='\n'.join(lines), choice=(output or {}).get('choice'), citations=list(dict.fromkeys(citations)),
                limitations=limitations, items=[dict(public_item=p, **restored[p['id']]) for p in run['answer_items']])


def source_quote_answer(service, run, request, source_evidence, source_versions, reference_map, requirements=()):
    """Experimental extractive answers: the model selects, the server quotes."""
    evidence = {f't{i + 1}': row for i, row in enumerate(source_evidence)}
    if not evidence:
        return None
    public_requirements = public_answer_requirements(requirements)
    requested_text = [request.question, *(r[k] for r in public_requirements for k in ('question', 'criterion'))]
    row = create_model('SourceAnswerItem', question_quote=(str, Field(min_length=1)),
        coverage=(Literal['direct', 'partial', 'unknown'], Field(...)),
        evidence_refs=(list[Literal[tuple(evidence)]], Field(...)),
        missing_question_quote=(str, Field(description='Exact question fragment whose answer is not directly established; empty only for direct coverage.')))
    response_type = create_model('SourceAnswerSelection', items=(list[row], Field(min_length=1)),
                                 choice=(Literal['A', 'B', 'C', 'D'] | None, None))
    output = business_run.json_call(service, run, 'business_qa',
        '질문과 public_requirements의 question/criterion이 요청한 모든 항목에 직접 답하는 원문과 그 주체·조건·예외를 선택한다. 원문 주소를 선택하며 답변 문장은 쓰지 않는다. '
        'question_quote는 질문 또는 공개 criterion의 정확한 구절이다. 대상/상황/기간은 적용 문맥이며 새 답변 항목이 아니다. '
        'evidence_refs에는 답과 주체·조건·예외를 함께 해석하는 데 필요한 구간을 고른다. '
        '원문의 기간 안내가 별도 행위의 허용 여부를 답하지 않으며, 조건부 의무는 조건 밖의 일반 의무를 답하지 않는다. '
        '허용·의무·제외를 물으면 그 효과가 직접 명시된 구간이 필요하다. 인접 업무나 묵시적 추론으로 direct를 선언하지 않는다. '
        '직접 답은 direct, 일부만 확인되면 partial, 직접 답을 확인할 수 없으면 unknown이다. '
        'partial/unknown은 missing_question_quote에 직접 확인하지 못한 질문 또는 criterion 구절을 표시한다. 요청 항목을 생략하지 않는다. '
        '관련 사실의 원문은 함께 선택할 수 있지만 답을 확인한 것으로 분류하지 않는다. '
        '같은 원문의 다른 절을 과잉 인용하지 않되 주체/조건/예외를 빠뜨리지 않는다. choice는 선택지가 있을 때만 고른다.',
        dict(question=request.question, choices=request.choices, public_requirements=public_requirements, source_versions=source_versions,
             source_evidence=[dict(reference=ref, **value) for ref, value in evidence.items()]),
        response_type, reference_map=reference_map)
    run['answer_contract'] = 'source-selection-server-quotation-experimental-v1'
    run['answer_selection'] = deepcopy(output)
    if not output:
        return None
    lines, citations, limitations = [], [], []
    for item in output['items']:
        if not any(item['question_quote'] in text for text in requested_text) or (item['missing_question_quote']
                and not any(item['missing_question_quote'] in text for text in requested_text)):
            return None
        if item['coverage'] == 'direct' and (not item['evidence_refs'] or item['missing_question_quote']):
            return None
        if item['coverage'] != 'direct' and not item['missing_question_quote']:
            return None
        lines.append(item['question_quote'])
        for ref in dict.fromkeys(item['evidence_refs']):
            source = evidence[ref]
            lines.append('원문: ' + source['text'])
            citations.extend(cid for link in source['claim_references'] for cid in link['claim_ids'])
        if item['coverage'] != 'direct':
            limitation = '직접 확인 불가: ' + item['missing_question_quote']
            lines.append(limitation)
            limitations.append(limitation)
    return dict(answer='\n\n'.join(lines), choice=output['choice'],
                citations=list(dict.fromkeys(citations)), limitations=limitations)


def query(service, request, *, context_mode='graph'):
    """The same question/answer contract supports a recorded document baseline."""
    from .discovery_profile import FrozenIndex
    if request.answer_mode in {'source_quotes', 'items', 'reviewed_items'} and (request.source_run_id or context_mode != 'graph'):
        raise ValueError('원문 선택 답변 실험은 승인 그래프 근거에서만 지원합니다.')
    started = monotonic()
    source_reader = bool(request.source_run_id)
    if context_mode not in {'graph', 'document'}:
        raise ValueError('Unknown query context')
    if context_mode == 'document' and request.retrieval != 'bm25':
        raise ValueError('문서 기준선은 bm25를 사용합니다. 그래프 검색은 graph 경로를 선택하세요.')
    with service.lock, service.repository.connect() as db:
        if service.closed or any(json.loads(r['payload'])['status'] in {'queued', 'running', 'cancel_requested'}
                                 for r in db.execute('SELECT payload FROM runs')):
            raise KnowledgeConflict('다른 실행이 종료된 뒤 답변을 요청하세요.')
        if source_reader:
            original = service.repository.get(db, 'runs', request.source_run_id)
            if original.get('kind') != 'business' or original['status'] not in {'succeeded', 'partial', 'failed', 'cancelled'}:
                raise ValueError('종료된 업무 지식 추출 실행을 선택하세요.')
            # A transient read view, never an approval or a stored snapshot.
            snapshot = dict(id='run:' + original['id'], kind='source_graph', run_id=original['id'],
                source_versions=original['sources'], blocks=original['blocks'],
                claims=[c for c in original['claims'] if not c.get('superseded_by') and not c.get('extraction_error')],
                concepts=original['concepts'], requirements=[], assessments={}, include_unlinked_blocks=True)
        else:
            snapshot = service.repository.get(db, 'snapshots', request.snapshot_id)
        if snapshot.get('kind') != 'source_graph':
            raise ValueError('출처 그래프 snapshot이 필요합니다.')
        invalidations = [event for row in db.execute('SELECT payload FROM snapshot_events')
            if (event := json.loads(row['payload'])).get('event') == 'business_correction'
            and event['snapshot_id'] == snapshot['id']]
        if invalidations:
            affected = {rid for i in invalidations for rid in i['requirement_ids']}
            if affected.intersection(request.requirement_ids):
                return dict(status='needs_review', answer=None, snapshot_id=snapshot['id'], invalidations=invalidations)
            excluded = {cid for i in invalidations for cid in i['claim_ids']}
            snapshot = dict(snapshot, claims=[c for c in snapshot['claims'] if c['id'] not in excluded],
                            assessments={rid:a for rid,a in snapshot['assessments'].items() if rid not in affected})
        if not set(request.requirement_ids) <= {r['id'] for r in snapshot['requirements']}:
            raise ValueError('선택한 요구가 해당 snapshot에 없습니다.')
        original = service.repository.get(db, 'runs', snapshot['run_id'])
        restrictions = restricted_sources(db, snapshot['source_versions'])
        if restrictions:
            return dict(status='needs_review', restrictions=restrictions, answer=None, snapshot_id=snapshot['id'])
        requirements = [service.repository.get(db, 'requirements', r['id']) for r in snapshot['requirements']
                        if not request.requirement_ids or r['id'] in request.requirement_ids]
        stale = [r['id'] for r in requirements if r['status'] == 'needs_review' or
                 r['revision'] != next(v['revision'] for v in snapshot['requirements'] if v['id'] == r['id'])]
        if stale:
            return dict(status='needs_review', requirement_ids=stale, answer=None, snapshot_id=snapshot['id'])
        answer_items = bind_answer_items(request, requirements)
        if context_mode == 'graph' and not snapshot['claims'] and not source_reader:
            return dict(status='no_reviewed_claims', answer=None, snapshot_id=snapshot['id'], model_called=False)
        if source_reader and not any(c.get('evidence') for c in snapshot['claims']) and not snapshot['blocks']:
            return dict(status='no_source_passages', answer=None, source_run_id=request.source_run_id, model_called=False)
        required_ids = set()
        if context_mode == 'graph' and request.requirement_ids:
            required_ids.update(cid for e in snapshot.get('explicit_meaning_reviews', [])
                if e['requirement_id'] in request.requirement_ids and e['meaning'].get('required_for_requirement')
                for cid in e['claim_ids'])
            for rid in request.requirement_ids:
                representation = snapshot['assessments'][rid].get('representation') or {}
                keys = {row['meaning_key'] for row in representation.get('source_checks', [])
                        if row['required_for_requirement']}
                required_ids.update(cid for row in representation.get('checks', [])
                    if row['meaning_key'] in keys and row['status'] == 'represented' for cid in row['claim_ids'])
            required_ids.intersection_update(c['id'] for c in snapshot['claims'])
            if len(required_ids) > request.limit:
                raise ValueError(f'필수 승인 후보 {len(required_ids)}개가 검색 한도 {request.limit}개를 넘습니다. 요구 범위 또는 한도를 조정하세요.')
        run = dict(id=uuid4().hex, kind='business_query', status='running', units=[], input_version_ids=list(snapshot['source_versions']),
                   recipe=deepcopy(original['recipe']), model_identity=original['model_identity'],
                   metrics=dict(llm_calls=0, model_total_s=0, elapsed_s=0), started_at=utcnow(), finished_at=None,
                   query=request.model_dump(), answer_items=answer_items, context_mode=context_mode, snapshot_id=snapshot['id'],
                   answer_basis='source_passages_not_ontology_approval' if source_reader else 'reviewed_claims',
                   source_extraction_status=original['status'] if source_reader else None,
                   answer_contract=ANSWER_CONTRACT, required_context_ids=sorted(required_ids))
        db.execute('INSERT INTO runs VALUES(?,?)', (run['id'], encode(run)))
    if source_reader:
        from . import graph_retrieval
        _, _, passages, _ = graph_retrieval.build(snapshot, request.graph_variant)
        candidates = graph_retrieval.passage_candidates(passages)
    elif context_mode == 'graph':
        candidates = [dict(id=c['id'], text=encode(business_run.compact_claim(c)),
                           file_id=c['source_version_ids'][0], source_group=c['source_version_ids'][0]) for c in snapshot['claims']]
    else:
        candidates = [dict(id=b['id'], text=b['text'], file_id=b['source_version_id'],
                           source_group=b['source_version_id']) for b in snapshot['blocks']]
    hints = concept_hints(snapshot) if context_mode == 'graph' and not source_reader else {}
    if request.retrieval == 'bm25':
        if source_reader:
            search_texts = graph_retrieval.passage_search_texts(candidates, snapshot['blocks'], run['recipe']['options'])
            run['passage_index'] = dict(contract=graph_retrieval.INDEX_CONTRACT, texts=search_texts)
            index_candidates = [dict(c, text=search_texts[c['id']]) for c in candidates]
        else:
            index_candidates = [dict(c, text=c['text'] + '\n검색용 관련 표현: ' + ', '.join(hints.get(c['id'], [])))
                                if hints.get(c['id']) else c for c in candidates]
        index = FrozenIndex(index_candidates, preserve_numbers=True)
        query_text = request.question + '\n' + '\n'.join(request.choices)
        allowed_ids = {c['id'] for c in candidates}
        hits = index.rank(query_text, allowed_ids) if source_reader else index.search(query_text, allowed_ids, request.limit)
    else:
        from . import graph_retrieval
        try:
            hits = graph_retrieval.retrieve(service, run, snapshot, request)
        except Exception as exc:
            run.update(status='failed', finished_at=utcnow(), error=f'{type(exc).__name__}: {exc}')
            run['metrics']['elapsed_s'] = monotonic() - started
            business_run.save(service, run)
            return dict(run_id=run['id'], status='retrieval_failed', answer=None,
                        snapshot_id=snapshot['id'], error=run['error'])
    if source_reader:
        hits, run['passage_selection'] = graph_retrieval.select_passages(
            candidates, hits, snapshot['blocks'], run['recipe']['options'], request.limit)
    if required_ids:
        by_id = {h['block_id']: h for h in hits}
        mandatory = [dict(by_id.get(c['id']) or dict(block_id=c['id'], file_id=c['file_id'], score=None),
                          selection_reason='required_reviewed_meaning') for c in candidates if c['id'] in required_ids]
        hits = mandatory + [h for h in hits if h['block_id'] not in required_ids][:request.limit - len(mandatory)]
    selected = {h['block_id'] for h in hits}
    context = [c for c in candidates if c['id'] in selected]
    if not context:
        run.update(status='partial', finished_at=utcnow(), answer=None, answer_status='unverified',
                   retrieval=hits, provided_ids=[])
        run['metrics']['elapsed_s'] = monotonic() - started
        business_run.save(service, run)
        return dict(run_id=run['id'], status='unverified', answer=None, retrieval=hits,
                    context_mode=context_mode, snapshot_id=None if source_reader else snapshot['id'],
                    source_run_id=request.source_run_id, answer_basis=run['answer_basis'], qa_model_called=False)
    reviewed_meanings = reviewed_answer_meanings(snapshot, selected, request.requirement_ids) if not source_reader else []
    run['answer_scope_contract'] = 'reviewed-meanings-and-source-qualifications-v1'
    run['reviewed_meanings'] = deepcopy(reviewed_meanings)
    if request.answer_mode == 'reviewed_items':
        run['exact_row_answer_fields'] = exact_row_answer_fields(snapshot, selected, request.requirement_ids)
    required_source_context = []
    if source_reader:
        context = [{k: v for k, v in c.items() if k != 'linked_claim_ids'} for c in context]
        required_source_context = graph_retrieval.source_context(snapshot['blocks'], context, run['recipe']['options'])
        run['source_context_contract'] = 'existing-table-rowspan-heading-list-bundles-v1'
        run['source_context'] = deepcopy(required_source_context)
    source_evidence = {}
    if context_mode == 'graph' and not source_reader:
        blocks = {b['id']: b for b in snapshot['blocks']}
        review_chunks = business_run.autoschema.chunks(snapshot['blocks'], run['recipe']['options']['context_tokens'],
            run['recipe']['options']['review_tokens'], 1) if reviewed_meanings else []
        for claim in snapshot['claims']:
            if claim['id'] not in selected:
                continue
            meanings = [m for m in reviewed_meanings if claim['id'] in m['claim_ids'] and not m['record_error']
                        and m['source_status'] == 'supported' and m['availability'] == 'provided'
                        and (m.get('requirement_link') or {}).get('applicability') != 'unresolved'
                        and m['expression_status'] == 'represented' and m['claim_support'][claim['id']] == 'supported']
            meaning_refs = []
            if meanings and any(m['evidence'] for m in meanings):
                scoped = business_review.related_blocks(dict(blocks=snapshot['blocks'], recipe=run['recipe']),
                                                        meanings, chunks=review_chunks)
                meaning_refs = [business_run.exact_evidence([dict(block_id=b['id'], quote=b['text'])], [b])[0]
                                for b in scoped]
            # Chunk references locate extraction input. For an explicitly reviewed
            # meaning retain the whole source unit and its existing mandatory
            # context. Partial/unknown judgments cannot replace the chunk source.
            refs = [e for e in claim.get('evidence', []) if not meaning_refs or e.get('precision') != 'chunk']
            for ref in [*refs, *meaning_refs]:
                key = json.dumps(ref, ensure_ascii=False, sort_keys=True)
                row = source_evidence.setdefault(key, dict(evidence=deepcopy(ref),
                    locator=deepcopy(blocks.get(ref['block_id'], {}).get('locator', {})), claim_ids=[]))
                if claim['id'] not in row['claim_ids']:
                    row['claim_ids'].append(claim['id'])
    evidence_rows = list(source_evidence.values())
    views = [dict(id=row['evidence']['block_id'], text=row['evidence']['quote'],
        source_version_id=row['evidence']['source_version_id'], parse_run_id=row['evidence'].get('parse_run_id'),
        span=[row['evidence']['start_char'], row['evidence']['end_char']]) for row in evidence_rows]
    source_evidence = []
    for block_id in dict.fromkeys(view['id'] for view in views):
        for view in business_run.contiguous_evidence_views(views, block_id):
            # The enclosing view already carries source/version/parse/block IDs.
            # Keep each claim's exact span without repeating those addresses.
            links = [dict(claim_ids=row['claim_ids'], span=[row['evidence']['start_char'], row['evidence']['end_char']],
                          precision=row['evidence'].get('precision', 'unspecified'))
                for row in evidence_rows if row['evidence']['block_id'] == block_id
                and row['evidence']['source_version_id'] == view['source_version_id']
                and row['evidence'].get('parse_run_id') == view.get('parse_run_id')
                and view['span'][0] <= row['evidence']['start_char'] < row['evidence']['end_char'] <= view['span'][1]]
            source_evidence.append(dict(view, claim_references=links))
    references = {c['id']: f'q{i+1}' for i, c in enumerate(context)}
    citation_type = list[Literal[tuple(references)]] if references else list[str]
    context_answer = create_model('ContextAnswer', __base__=SourceAnswer if source_reader else Answer,
        citations=(citation_type, Field(max_length=len(context), json_schema_extra={'uniqueItems': True})))
    # Reuse the existing reversible reference map for long source addresses too.
    # Citation choices remain context IDs; the server restores original IDs.
    reference_map = dict(references)
    if source_reader:
        reference_map.update({c['id']: f'c{i+1}' for i, c in enumerate(snapshot['claims'])})
    source_addresses = source_evidence + required_source_context + [dict(id=c['source_reference']['block_id'], **{
        k: c['source_reference'].get(k) for k in ('source_version_id', 'parse_run_id')})
        for c in context if 'source_reference' in c]
    for field, prefix in [('id', 'b'), ('source_version_id', 'v'), ('parse_run_id', 'p')]:
        values = list(dict.fromkeys(v[field] for v in source_addresses if v.get(field)))
        reference_map.update({value: f'{prefix}{i+1}' for i, value in enumerate(values) if value not in reference_map})
    # Complete claim bundles retain conditions and source provenance; no gold mappings.
    limitations = [dict(requirement_id=r, status=a['status'], gaps=(a.get('source') or {}).get('gaps', []))
                   for r, a in snapshot['assessments'].items() if a['status'] != 'satisfied']
    answer_requirements = public_answer_requirements(requirements) if request.requirement_ids else []
    if request.answer_mode == 'reviewed_items':
        run['answer_assessment_limitations'] = [dict(requirement_id=r['id'], period=r.get('period', ''),
            status=a['status'], source_completeness=(a.get('source') or {}).get('completeness', 'unknown'),
            synthesis_source_completeness=(a.get('representation') or {}).get('source_completeness', 'unknown'),
            review_notes=unresolved_finding_notes(a.get('source') or {}),
            finding_resolutions=deepcopy((a.get('source') or {}).get('finding_resolutions', [])),
            synthesis_reason=(a.get('representation') or {}).get('reason', ''),
            gaps=(a.get('source') or {}).get('gaps', [])) for r in requirements
            if (a := snapshot['assessments'][r['id']])['status'] != 'satisfied']
        output = reviewed_item_answer(service, run, request, answer_requirements)
    elif request.answer_mode == 'items':
        output = item_answer(service, run, request, source_evidence, snapshot['source_versions'], reference_map, answer_requirements)
    elif request.answer_mode == 'source_quotes':
        output = source_quote_answer(service, run, request, source_evidence, snapshot['source_versions'], reference_map, answer_requirements)
    else:
        output = business_run.json_call(service, run, 'business_qa',
            '제공된 검색 근거만으로 질문에 한국어로 답한다. 선택지가 있으면 choice에 선택지의 A/B/C/D를 반환한다. '
            '부족하면 확인 불가와 구체 한계를 표시한다. citations에는 사용한 context id만 쓴다. '
            '각 인용 ID는 한 번만 쓰며 제공된 context 개수를 넘지 않는다. 빈 답변을 반환하지 않는다. '
            '미승인 개념이나 원문보다 강한 효과를 사실로 쓰지 않는다. 조건/예외/기간을 유지한다. '
            'source_evidence는 연결된 승인 후보의 출처와 범위를 확인하는 원문이다. '
            '같은 인용 안의 다른 의미까지 승인된 것으로 취급하지 않는다.' + (
            'public_requirements의 question/criterion은 공개 답변 기준이다. 기준에서 요청한 항목도 답하거나 구체 공백을 표시한다. '
            '대상·상황·시점은 적용 범위이며 기준 자체를 원문 근거나 정답으로 사용하지 않는다.' if answer_requirements else '') + (
            'reviewed_meanings는 기존 검수의 주장·조건·예외·기간과 원문을 연결한 범위이지 정답표가 아니다. '
            '질문에 해당하는 의미와 실제 인용을 함께 사용하고, 후보의 다른 절이나 검수 문장의 확대 해석을 그대로 확정하지 않는다. '
            '원문에서 직접 확인되는 사실과 추가 해석이 필요한 결론을 구분해 답한다.' if not source_reader else '') + (
            '\n이번 context는 검색된 원문 구간이다. 원문 자체를 대조하여 답한다. '
            'source_context는 선택한 구간의 표 행·병합 셀·상위 조건·예외에 필요한 원문이다. '
            'supports_context_ids와 표의 row/column/merged_span을 사용하여 귀속을 확인한다. '
            'context_id만 있는 문맥은 같은 context의 원문을 참조한다. 문맥 근거도 연결된 context id로 인용한다. '
            '검색에 사용한 그래프 연결은 미승인 추출일 수 있으며 그 존재가 의미 검증은 아니다. '
            '원문에 없는 조건이나 연결을 추론해서 채우지 않는다. 이 답변은 온톨로지 승인이나 업무 요구 전체 충족 판정이 아니다.'
            if source_reader else ''),
            dict(question=request.question, choices=request.choices, context=context,
                 source_versions=snapshot['source_versions'], source_evidence=source_evidence,
                 **({'public_requirements': answer_requirements} if answer_requirements else {}),
                 requirement_limitations=limitations, **({'source_context': required_source_context} if source_reader
                                                         else {'reviewed_meanings': reviewed_meanings})), context_answer,
            reference_map=reference_map)
    if source_reader:
        run['answer_contract'] = 'source-unique-provided-citations-lossless-dedup-v3'
        raw_ids = ((run['units'][-1].get('response') or {}).get('parsed') or {}).get('citations', []) if run['units'] else []
        if output and isinstance(raw_ids, list) and all(isinstance(v, str) for v in raw_ids):
            run['citation_normalization'] = dict(kind='stable_dedup_only',
                removed_duplicates=len(raw_ids) - len(set(raw_ids)))
    status = 'answered'
    if not output or run.get('answer_item_errors') or not set(output['citations']) <= selected or (output['answer'] and not output['citations']):
        status = 'unverified'
    with service.lock, service.repository.connect() as db:
        now = [service.repository.get(db, 'requirements', r['id']) for r in requirements]
        if restricted_sources(db, snapshot['source_versions']) or any(
                n['revision'] != r['revision'] or n['status'] == 'needs_review' for n, r in zip(now, requirements)):
            status, output = 'needs_review', None
        run.update(status='succeeded' if status == 'answered' else 'partial', finished_at=utcnow(),
                   answer=output, answer_status=status, retrieval=hits, provided_ids=sorted(selected),
                   retrieval_concept_hints=hints, retrieval_contract=('required-reviewed-claims+ranked-remainder-v1' if context_mode == 'graph' and request.requirement_ids
                                       else 'source-claims+concept-hints+numeric-identifiers-v2'),
                   concept_hints_are_answer_evidence=False)
        if request.retrieval != 'bm25':
            run.update(retrieval_contract=run['graph_retrieval']['contract'], retrieval_concept_hints={})
        elif source_reader:
            run['retrieval_contract'] = 'bm25-source-passages-raw-ranking-v2'
        run['metrics']['elapsed_s'] = monotonic() - started
        service.repository.save(db, 'runs', run)
    return dict(run_id=run['id'], status=status, answer=output, retrieval=hits,
                context_mode=context_mode, snapshot_id=None if source_reader else snapshot['id'],
                source_run_id=request.source_run_id, answer_basis=run['answer_basis'], limitations=limitations)
