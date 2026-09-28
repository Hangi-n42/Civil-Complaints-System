"""LH source mapping and bounded fact output; no model-driven table reconstruction."""
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re

PROFILE = json.loads((Path(__file__).resolve().parents[2] / 'configs/knowledge/k4_lh_mapping.json').read_text(encoding='utf-8'))
FIELDS = PROFILE['fields']
MONTHS = set(PROFILE['months'])


def compatible(definitions, slot):
    actual = {d['id']: d for d in definitions}
    expected = PROFILE['definitions'].get(slot)
    if not expected or slot not in actual:
        return False
    ids = [slot, expected.get('domain_id')]
    if expected.get('kind') == 'relation':
        ids.append(expected.get('range'))
    return all(i in actual and all(actual[i].get(k) == v for k, v in PROFILE['definitions'][i].items())
               for i in ids if i)


def normalize(raw, definition):
    """Only literal formatting; never infer missing date precision or quantity scope."""
    text = str(raw).strip()
    slot, kind = definition['id'], definition.get('range', 'string')
    if definition.get('multivalued'):
        raise ValueError('다중값 슬롯은 이 추출 계약에서 지원하지 않습니다.')
    if slot in MONTHS:
        match = re.fullmatch(r'(\d{4})[.\-/]?(\d{2})', text)
        if not match:
            raise ValueError('월 원문은 YYYYMM 또는 YYYY-MM이어야 합니다.')
        date(int(match[1]), int(match[2]), 1)
        return f'{match[1]}-{match[2]}', None
    if kind in {'integer', 'float', 'double', 'decimal'}:
        match = re.fullmatch(r'([+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)\s*(세대|호|개동|동|개|명|원|%)?', text)
        if not match:
            raise ValueError('숫자 원문을 해석할 수 없습니다.')
        number = match[1].replace(',', '')
        value = int(number) if kind == 'integer' else float(number)
        return value, match[2]
    if kind == 'date':
        match = re.fullmatch(r'(\d{4})[.\-/](\d{2})[.\-/](\d{2})', text)
        if not match:
            raise ValueError('일 정밀도 원문이 필요합니다.')
        return date(*map(int, match.groups())).isoformat(), None
    if kind == 'boolean':
        if text.lower() not in {'true', 'false'}:
            raise ValueError('명시적인 boolean 원문이 필요합니다.')
        return text.lower() == 'true', None
    return text, None


def table_key(block):
    loc = block['locator']
    return (block.get('source_version_id'), block.get('parse_run_id', block.get('run_id')),
            loc.get('physical_page'), loc.get('side'), loc.get('table'))


def reference(block):
    return dict(block_id=block['id'], quote=block['text'])


def pdf_records(run, unit):
    blocks = [b for b in run['frozen_blocks'] if b['id'] in unit['block_ids']]
    groups = {}
    for b in blocks:
        groups.setdefault(table_key(b), []).append(b)
    records, coverage = [], []
    definitions = {d['id']: d for d in run['ontology_candidates']}
    for key, cells in groups.items():
        headers = {b['text'].strip(): b for b in cells if b['locator'].get('row') == 0}
        supported = all(h in headers for h in PROFILE['pdf_columns'])
        rows = sorted({b['locator'].get('row') for b in cells if isinstance(b['locator'].get('row'), int) and b['locator']['row'] > 0})
        if not rows:
            coverage.append(dict(id=str(key), status='unsupported', reason='지원하는 단지 표 구조가 없습니다.'))
        for row in rows:
            data = [b for b in cells if b['locator'].get('row') == row]
            subject = next((b for b in data if supported and b['locator'].get('column') == headers['단지명']['locator'].get('column')), None)
            # ponytail: this pilot supports single-row data cells; new merged layouts need an explicit mapping.
            layout_ok = supported and subject and all(b['locator'].get('merged_span', {}).get('rows', 1) == 1 for b in data)
            for title, spec in PROFILE['pdf_columns'].items():
                status = dict(id=f'{key}:{row}:{spec["slot"]}', row=row, predicate_id=spec['slot'], status='needs_review', reason='')
                coverage.append(status)
                if not layout_ok or not compatible(run['ontology_candidates'], spec['slot']):
                    status.update(status='unsupported', reason='표 구조 또는 검토된 속성 정의가 매핑과 맞지 않습니다.')
                    continue
                header = headers[title]
                col = header['locator']['column']
                span = header['locator'].get('merged_span', {}).get('columns', 1)
                values = [b for b in data if col <= b['locator'].get('column', -1) < col + span]
                if spec.get('unit'):
                    values = [b for b in values if re.fullmatch(r'[\d,]+\s*'+spec['unit'], b['text'].strip())]
                if len(values) != 1:
                    status['reason'] = '값 셀을 유일하게 지정할 수 없습니다.'
                    continue
                b = values[0]
                try:
                    value, unit_name = normalize(b['text'], definitions[spec['slot']])
                except ValueError as exc:
                    status['reason'] = str(exc)
                    continue
                records.append(dict(concept_id='CONCEPT_001', mention=subject['text'], official_id=None,
                    subject_evidence=[reference(subject)], values={spec['slot']: value}, raw_values={spec['slot']: b['text']},
                    field_evidence={spec['slot']: [reference(b)], 'scope': [reference(header)]},
                    unit=unit_name, scope=f'PDF 단지 현황 표 · {title}', conditions=[], exceptions=[]))
                status.update(status='extracted', block_id=b['id'])
    return records, coverage


def text_units(run, unit):
    groups = {}
    for b in run['frozen_blocks']:
        if b['id'] in unit['block_ids']:
            groups.setdefault((b['source_version_id'], b['locator'].get('official_code') or b['id']), []).append(b)
    return [dict(id=f't{i}', blocks=rows, code=rows[0]['locator'].get('official_code')) for i, rows in enumerate(groups.values())]


def fact_definitions(run, unit=None):
    selected = [b for b in run['frozen_blocks'] if unit and b['id'] in unit['block_ids']]
    limited = selected and all(b['locator'].get('field')=='imgAhflDesc' for b in selected)
    return [d for d in run['ontology_candidates'] if d['kind'] in {'attribute', 'relation'} and (d['kind']=='relation' or not d.get('multivalued'))
            and d['id'] not in {'ATTRIBUTE_001', 'ATTRIBUTE_002', 'NoticeIdentifier'}
            and (not limited or d['id'] in PROFILE['html_description_slots'])]


def schema(run, unit):
    refs = {b['id']: f'b{i}' for i, b in enumerate(run['frozen_blocks'])}
    allowed = [refs[b] for b in unit['block_ids']]
    ev = dict(type='array', items=dict(type='object', properties={'block_id': {'type':'string','enum':allowed},
               'quote':{'type':'string','minLength':1}}, required=['block_id','quote'], additionalProperties=False))
    nonempty_ev = dict(ev, minItems=1)
    variants = []
    for d in fact_definitions(run,unit):
        props = dict(predicate_id={'type':'string','const':d['id']}, evidence=nonempty_ev,
                     scope={'type':'string'}, scope_evidence=ev, unit={'type':['string','null'], 'enum':['세대','호',None]},
                     conditions={'type':'array','items':{'type':'string'}}, conditions_evidence=ev,
                     exceptions={'type':'array','items':{'type':'string'}}, exceptions_evidence=ev)
        if d['kind'] == 'relation':
            props['object'] = dict(type='object', properties=dict(mention={'type':'string'}, concept_id={'type':'string','const':d['range']},
                                   official_id={'type':['string','null']}, evidence=nonempty_ev), required=['mention','concept_id','official_id','evidence'], additionalProperties=False)
        else:
            props['raw_value'] = {'type':'string','minLength':1}
        variants.append(dict(type='object', properties=props, required=list(props), additionalProperties=False))
    subject = dict(type='object',properties=dict(mention={'type':'string'}, concept_id={'type':'string','enum':[d['id'] for d in run['ontology_candidates'] if d['kind']=='concept']},
                   official_id={'type':['string','null']}, evidence=ev),required=['mention','concept_id','official_id','evidence'],additionalProperties=False)
    props = dict(unit_id={'type':'string','enum':[g['id'] for g in text_units(run,unit)]},
                 subject=subject, facts={'type':'array','items':{'anyOf':variants} if variants else False}, reason={'type':'string'})
    return dict(type='object', properties={'units':dict(type='array',items=dict(type='object',properties=props,required=list(props),additionalProperties=False))}, required=['units'],additionalProperties=False)


def adapt(run, unit, decoded):
    """Bind raw facts to frozen input; preserve invalid facts and missing units for review."""
    from jsonschema import Draft202012Validator
    groups = {g['id']:g for g in text_units(run,unit)}
    refs = {f'b{i}': b for i,b in enumerate(run['frozen_blocks'])}
    definitions = {d['id']:d for d in fact_definitions(run,unit)}
    outputs = decoded.get('units') if isinstance(decoded,dict) else None
    if not isinstance(outputs,list):
        raise ValueError('units 배열이 필요합니다.')
    counts = Counter(o.get('unit_id') for o in outputs if isinstance(o,dict) and isinstance(o.get('unit_id'),str))
    records, coverage, invalid = [], [], []
    for identifier, g in groups.items():
        coverage.append(dict(id=identifier, block_ids=[b['id'] for b in g['blocks']], status='missing' if not counts[identifier] else 'duplicate' if counts[identifier]>1 else 'returned', reason=''))
    validator = Draft202012Validator(schema(run,unit))
    for index, output in enumerate(outputs):
        shape = dict(output,facts=[]) if isinstance(output,dict) and isinstance(output.get('facts'),list) else output
        errors = [e.message for e in validator.iter_errors({'units':[shape]})]
        if errors:
            invalid.append(dict(index=index,raw_record=output,validation_errors=errors));continue
        identifier = output['unit_id']
        if identifier not in groups or counts[identifier]!=1:
            invalid.append(dict(index=index,raw_record=output,validation_errors=['unknown_or_duplicate_unit']));continue
        g = groups[identifier]
        allowed = {b['id'] for b in g['blocks']}
        def check_evidence(items):
            if any(refs.get(e['block_id'],{}).get('id') not in allowed for e in items):
                raise ValueError('근거가 해당 설명 단위 밖에 있습니다.')
        subject = output['subject']
        if g['code']:
            code = g['code']
            support = next((b for b in run['frozen_blocks'] if code in b['text'] and
                           (b['locator'].get('script_array')=='sbdList' or b['locator'].get('format')=='csv') and b['locator'].get('official_code')==code), None)
            entity = next((e for e in run['entities'] if e.get('official_id')==code), None)
            if not support or not entity:
                invalid.append(dict(index=index,raw_record=output,validation_errors=['official_subject_context_missing']));continue
            subject = dict(mention=entity['name'], concept_id=entity['concept_id'], official_id=code, evidence=[reference(support)])
        else:
            try:check_evidence(subject['evidence'])
            except ValueError as exc:
                invalid.append(dict(index=index,raw_record=output,validation_errors=[str(exc)]));continue
        before = len(records)
        invalid_before = len(invalid)
        for fact in output['facts']:
            try:
                errors = [e.message for e in validator.iter_errors({'units':[dict(output,facts=[fact])]})]
                if errors:
                    raise ValueError('; '.join(errors))
                for field in ('evidence','scope_evidence','conditions_evidence','exceptions_evidence'):
                    check_evidence(fact[field])
                definition = definitions[fact['predicate_id']]
                if definition['domain_id'] != subject['concept_id']:
                    raise ValueError('주체 유형과 속성 정의가 다릅니다.')
                if fact['scope'] not in {'','미확인'} and not fact['scope_evidence']:
                    raise ValueError('범위 근거가 없습니다.')
                if definition['kind']=='relation':
                    check_evidence(fact['object']['evidence'])
                    value, unit_name = fact['object'], None
                else:
                    value, unit_name = normalize(fact['raw_value'],definition)
                slot = definition['id']
                records.append(dict(concept_id=subject['concept_id'],mention=subject['mention'],official_id=subject['official_id'],subject_evidence=subject['evidence'],
                    values={slot:value},raw_values={slot:fact.get('raw_value')},
                    field_evidence={slot:fact['evidence'],'scope':fact['scope_evidence'],'conditions':fact['conditions_evidence'],'exceptions':fact['exceptions_evidence']},
                    scope=fact['scope'],unit=unit_name or fact['unit'],conditions=fact['conditions'],exceptions=fact['exceptions']))
            except (ValueError,KeyError) as exc:
                invalid.append(dict(index=index,raw_record=fact,validation_errors=[str(exc)]))
        next(c for c in coverage if c['id']==identifier).update(status='extracted' if len(records)>before and len(invalid)==invalid_before else 'needs_review', reason=output['reason'] if len(records)==before else ('일부 사실의 출력 계약 오류' if len(invalid)>invalid_before else ''), fact_count=len(records)-before)
    for c in coverage:
        if c['status']=='returned':c.update(status='needs_review',reason='출력 계약 오류')
    return records, coverage, invalid


def pdf_slot(run, block):
    """Known column role only; unrecognized tables have no inferred role."""
    headers = {b['text'].strip():b for b in run['frozen_blocks'] if table_key(b)==table_key(block) and b['locator'].get('row')==0}
    if not all(h in headers for h in PROFILE['pdf_columns']):
        return None
    col = block['locator'].get('column',-1)
    for title,spec in PROFILE['pdf_columns'].items():
        h=headers[title]['locator']
        if h['column']<=col<h['column']+h.get('merged_span',{}).get('columns',1):
            return spec['slot']
    return None
