"""K1: immutable addresses survive role, selection and resume changes."""
from copy import deepcopy
import json

import pytest

from app.knowledge import discovery_analysis as a2, discovery_segments as segments


def test_canonical_prompt_refs_survive_role_selection_and_resume():
    b = dict(id='block-id', text='첫 조건. 둘째 조건.', source_version_id='v', parse_run_id='p', locator={'page': 1})
    candidate = dict(id='candidate-id', classification='type', definition='역할', evidence_ids=[b['id']])
    context = dict(blocks=[dict(ref=b['id'], text=b['text'], span=[0,len(b['text'])])],
                   targets=[candidate], target_ids=[candidate['id']])
    before = deepcopy(context)
    run = dict(id='original-run', cqs=[], scope_items=[], recipe=dict(reference_contract='canonical-v1'))
    outputs = []
    for stage, run_id, supplied in [('critic','original-run',{candidate['id']:candidate}),
                                   ('revision','resumed-run',{'other':dict(id='other'),candidate['id']:candidate})]:
        mapping, prompt = a2.make_prompt(dict(run,id=run_id), stage, context, [b['id']], supplied, stage)
        data = json.loads(prompt.split('\nINPUT:\n')[1]); outputs.append(data)
        assert mapping[candidate['id']] == candidate['id'] and mapping[b['id']] == b['id']
        assert data['targets'][0]['id'] == candidate['id']
    assert outputs[0]['blocks'] == outputs[1]['blocks'] and context == before
    view = outputs[0]['blocks'][0]
    item = dict(source_refs=[view['source_ref']], evidence_ids=[b['id']])
    segments.restore(item, {b['id']:b}, outputs[1]['blocks'])
    assert item['evidence_refs'][0]['source_version_id'] == 'v'
    with pytest.raises(ValueError,match='제공되지 않은'):
        segments.restore(dict(source_refs=[view['source_ref']]), {b['id']:b}, [])


def test_stable_refs_distinguish_block_span_and_text_and_preserve_legacy():
    views = [dict(ref='b',text='반복',span=[0,2]),dict(ref='b',text='반복',span=[3,5]),
             dict(ref='b',text='변경',span=[0,2]),dict(ref='other',text='반복',span=[0,2])]
    a = segments.bind(dict(blocks=views),'run','critic:g',stable=True)
    z = segments.bind(dict(blocks=list(reversed(views))),'resumed','revision:g',stable=True)
    assert len({v['source_ref'] for v in a['blocks']}) == 4
    assert a['blocks'] == list(reversed(z['blocks']))
    legacy = segments.bind(dict(blocks=views),'run','critic:g')
    assert legacy != a and legacy == segments.bind(dict(blocks=views),'run','critic:g')
