from app.knowledge import discovery_segments as segments


def block(text):
    return dict(id='b',text=text,source_version_id='v',parse_run_id='p',locator={'page':1})


def test_seven_items_keep_shared_conditions_offsets_and_full_original():
    original='제2조 이 조의 유형은 다음과 같다. '+ ' '.join(f'{i}. 유형{i}의 정의.' for i in range(1,8))+' 다만 예외 조건은 유지한다.'
    b=block(original); parts=segments.split(b)
    assert len(parts)==4 and b['text']==original
    for part in parts:
        text=original[slice(*part['span'])]
        shared=' '.join(original[slice(*s)] for s in part['shared_spans'])
        assert '제2조' in shared and '다만 예외 조건은 유지한다.' in text+shared
        assert part['block_id']=='b' and part['recipe']==segments.VERSION
    covered=''.join(original[slice(*p['span'])] for p in parts)
    assert all(f'유형{i}의 정의.' in covered for i in range(1,8))


def test_unnumbered_bullets_and_ambiguous_unstructured_text():
    assert len(segments.split(block('공통 조건\n'+''.join(f'- 항목{i} 정의\n' for i in range(7)))))==4
    assert len(segments.split(block('경계없는원문'*500)))==1


def test_quote_must_exist_in_the_provided_parent_span():
    b=block('앞 문장. 주 분석 정의. 미제공 문장.')
    view=dict(ref='b',text=b['text'][6:14],span=[6,14])
    ref,errors=segments.references(dict(evidence_ids=['b'],source_quotes=[dict(evidence_id='b',quote='주 분석 정의.')]),{'b':b},[view])
    assert not errors and ref[0]['span']==[6,14] and ref[0]['locator']==b['locator']
    ref,errors=segments.references(dict(evidence_ids=['b'],source_quotes=[dict(evidence_id='b',quote='미제공 문장.')]),{'b':b},[view])
    assert not ref and errors


def test_nested_article_preserves_governing_clause_for_later_numbered_item():
    text='제15조 ① 기본 선정. ② 잔여 주택 완화. ③ 다음 각 호에 해당하면 장관 또는 시ㆍ도지사가 별도 기준을 정한다. 1. 첫 조건. 2. 둘째 조건. 3. 셋째 조건. 4. 지방공사 건설 공급.'
    parts=segments.split(block(text))
    assert len(parts)>1
    last=parts[-1]
    provided=text[slice(*last['span'])]+' '.join(text[slice(*s)] for s in last['shared_spans'])
    assert '4. 지방공사 건설 공급.' in provided and '장관 또는 시ㆍ도지사가 별도 기준을 정한다.' in provided
