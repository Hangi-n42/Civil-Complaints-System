"""Current candidate passages, source references and deterministic review aggregation.

Text coverage detects omissions, not semantic completeness or reason/verdict agreement.
"""
from copy import deepcopy

from . import discovery_models as models


def aggregate(values):
    values=list(values)
    return 'refuted' if 'refuted' in values else 'unknown' if not values or 'unknown' in values else 'supported'


def prepare(raw, candidate):
    if 'definition' in raw.get('semantic_checks', {}):
        raise ValueError('정의 최종 판정은 주장/충족 검사에서 서버가 집계')
    checks=raw.get('semantic_checks', {})
    if set(checks)!={'classification','conditions','exceptions'}:
        raise ValueError('관측 분류·조건·예외 판정 누락')
    # Validate before aggregation so an omitted/unknown enum cannot become supported.
    parsed=models.ClaimObservationCheck.model_validate(dict(raw,judgment='unknown')).model_dump()
    coverage={field:set() for field in ('definition','conditions','exceptions','time')}
    for claim in parsed['claim_reviews']:
        text=candidate.get(claim['field'], '')
        quote=claim['candidate_quote']
        if not text or text.count(quote)!=1:
            raise ValueError('검수 구절이 현재 후보에 없거나 위치가 모호함')
        start=text.index(quote)
        coverage[claim['field']].update(range(start,start+len(quote)))
    for field, covered in coverage.items():
        if any(not char.isspace() and i not in covered for i,char in enumerate(candidate.get(field, ''))):
            raise ValueError('현재 후보 검수 구절 누락: '+field)
    parsed['semantic_checks']['definition']=aggregate([
        *(c['judgment'] for c in parsed['claim_reviews']),parsed['definition_completeness']['judgment']])
    parsed['judgment']=aggregate(parsed['semantic_checks'].values())
    return parsed


def restore(item, candidate):
    """Called after the ordinary review model validates, using the same source ledger."""
    refs=list(item.get('evidence_refs', []))
    for claim in item['claim_reviews']:
        # The shared recursive restore already validated only actually supplied source refs.
        if claim['judgment']!='unknown' and not claim.get('evidence_refs'):
            raise ValueError('지지/반박 주장에는 정확한 제공 원문 필요')
        start=candidate[claim['field']].index(claim['candidate_quote'])
        claim['candidate_span']=[start,start+len(claim['candidate_quote'])]
        for ref in claim.get('evidence_refs', []):
            if ref not in refs: refs.append(deepcopy(ref))
    item['evidence_refs']=refs
    item['claim_coverage']='complete_text_only'
    # Aggregate reasons for the derived repair issue without trusting a free final verdict.
    failed=[c['field']+': '+c['candidate_quote']+' — '+c['reason'] for c in item['claim_reviews'] if c['judgment']=='refuted']
    if item['definition_completeness']['judgment']=='refuted':
        failed.append(item['definition_completeness']['reason'])
    if failed: item['reason']='; '.join(failed)


def revision_context(checks, fingerprint):
    claims=[deepcopy(c) for check in checks for c in check.get('claim_reviews', [])]
    return dict(target_fingerprint=fingerprint,
        failed_claims=[c for c in claims if c['judgment']=='refuted'],
        preserve_claims=[c for c in claims if c['judgment']=='supported'],
        unresolved_claims=[c for c in claims if c['judgment']=='unknown'])
