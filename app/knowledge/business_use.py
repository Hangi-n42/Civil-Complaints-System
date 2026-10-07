"""Review source claims without turning search concepts into approved ontology types."""
from copy import deepcopy
import json
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


def change_view(service, changeset_id):
    with service.repository.connect() as db:
        change = service.repository.get(db, 'changesets', changeset_id)
        if change.get('kind') != 'source_graph':
            raise ValueError('업무 지식 변경안이 아닙니다.')
        run = service.repository.get(db, 'runs', change['run_id'])
    eligible, blocked = review_eligibility(change, run)
    return dict(change, eligible_ids=sorted(eligible), published_eligible_ids=change['eligible_ids'],
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
        if not set(request.accept_ids) <= eligible:
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
    for rid, assessment in snapshot.get('assessments', {}).items():
        if requirement_ids and rid not in requirement_ids:
            continue
        checks = {c['meaning_key']: c for c in (assessment.get('representation') or {}).get('checks', [])}
        for meaning in (assessment.get('source') or {}).get('meanings', []):
            check = checks.get(meaning['key'], {})
            ids = sorted(selected.intersection(check.get('claim_ids', [])))
            if not ids:
                continue
            row = dict(requirement_id=rid, assessment_id=assessment['id'],
                claim_ids=ids, expression_status=check['status'], **{k: deepcopy(meaning.get(k)) for k in
                ('key', 'statement', 'conditions', 'exceptions', 'period', 'references', 'source_status',
                 'availability', 'record_error', 'requirement_link')})
            row['claim_support'] = {cid: check.get('claim_support', {}).get(cid, 'not_assessed') for cid in ids}
            try:
                row['evidence'] = business_run.exact_evidence(meaning['evidence'], snapshot['blocks'])
            except ValueError as exc:
                row.update(evidence=[], record_error=str(exc))
            rows.append(row)
    return rows


def query(service, request, *, context_mode='graph'):
    """The same question/answer contract supports a recorded document baseline."""
    from .discovery_profile import FrozenIndex
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
        if context_mode == 'graph' and not snapshot['claims'] and not source_reader:
            return dict(status='no_reviewed_claims', answer=None, snapshot_id=snapshot['id'], model_called=False)
        if source_reader and not any(c.get('evidence') for c in snapshot['claims']) and not snapshot['blocks']:
            return dict(status='no_source_passages', answer=None, source_run_id=request.source_run_id, model_called=False)
        required_ids = set()
        if context_mode == 'graph' and request.requirement_ids:
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
                   query=request.model_dump(), context_mode=context_mode, snapshot_id=snapshot['id'],
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
    output = business_run.json_call(service, run, 'business_qa',
        '제공된 검색 근거만으로 질문에 한국어로 답한다. 선택지가 있으면 choice에 선택지의 A/B/C/D를 반환한다. '
        '부족하면 확인 불가와 구체 한계를 표시한다. citations에는 사용한 context id만 쓴다. '
        '각 인용 ID는 한 번만 쓰며 제공된 context 개수를 넘지 않는다. 빈 답변을 반환하지 않는다. '
        '미승인 개념이나 원문보다 강한 효과를 사실로 쓰지 않는다. 조건/예외/기간을 유지한다. '
        'source_evidence는 연결된 승인 후보의 출처와 범위를 확인하는 원문이다. '
        '같은 인용 안의 다른 의미까지 승인된 것으로 취급하지 않는다.' + (
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
    if not output or not set(output['citations']) <= selected or (output['answer'] and not output['citations']):
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
