"""N2 isolated binding calls: HTTP contract and failure evidence, no A2 success units."""
from argparse import Namespace
from hashlib import sha256
import json

import httpx
import pytest

from app.knowledge import discovery_analysis as a2, discovery_profile as profile, discovery_segments as segments
from scripts import run_knowledge_critic_diagnostic as diagnostic


@pytest.mark.parametrize('mode',['valid','invalid','truncated','empty'])
def test_binding_diagnostic_records_http_and_failures_without_full_review(tmp_path,monkeypatch,mode):
    block=dict(id='b',text='행위자가 대상을 공급한다.',source_version_id='v',parse_run_id='p',locator=dict(line=1))
    context=segments.bind(dict(blocks=[dict(ref='b',text=block['text'],span=[0,len(block['text'])])]),'run','critic',stable=True)
    views=segments.originals(context);ref=views[0]['source_ref']
    body=json.dumps(context,ensure_ascii=False,separators=(',',':'))
    prompt=diagnostic.BINDING_PROMPT+'\nINPUT:\n'+body
    schema=diagnostic.binding_schema('r',['object'],[ref])
    case=dict(id='E-A',prompt=prompt,schema=schema,source_views=views,
        prompt_sha256=sha256(prompt.encode()).hexdigest(),schema_sha256=profile.digest(schema))
    output=tmp_path/'once';freeze_path=tmp_path/'freeze.json';freeze_path.write_text('{}')
    options=dict(model='local',think=True,temperature=0,num_ctx=32768,num_predict=8192)
    freeze=dict(endpoint='http://127.0.0.1:11434',model_digest='digest',input_chars=24000,http_timeout_s=300,
        original_hashes={},runtime_hashes={},settings=dict(thinking=dict(output=str(output),model_options=options,
        cases=['E-A','E-B'],http_calls=2,model_seconds=600)))
    def info(client,url,**kwargs):
        data=dict(models=[dict(name='local',digest='digest')]) if url.endswith('/api/tags') else dict(capabilities=['thinking'])
        return httpx.Response(200,json=data,request=httpx.Request('GET',url))
    payloads=[]
    async def generated(client,url,**kwargs):
        payloads.append(kwargs['json'])
        value=dict(candidate_ref='r',binding_checks=dict(object='supported'),binding_reasons=dict(object='원문 대상과 정의가 일치'),source_refs=[ref])
        if mode=='invalid':value['source_refs']=['not-provided']
        return httpx.Response(200,json=dict(response='' if mode=='empty' else json.dumps(value),thinking='local thought',
            done=True,done_reason='length' if mode=='truncated' else 'stop',prompt_eval_count=100,eval_count=40),request=httpx.Request('POST',url))
    monkeypatch.setattr(httpx.Client,'get',info);monkeypatch.setattr(httpx.Client,'post',info)
    monkeypatch.setattr(httpx.AsyncClient,'post',generated)
    monkeypatch.setattr(a2,'call',lambda *a,**kw:pytest.fail('A2 full Critic must not be called'))
    package=dict(blocks=[block],cases=[case,dict(case,id='E-B')])
    args=Namespace(setting='thinking',output=output,freeze=freeze_path)
    diagnostic.run_binding(args,freeze,package)
    assert len(payloads)==2 and all(p['think'] is True and p['prompt'].split('\nINPUT:\n')[1]==body for p in payloads)
    assert all(p['options']=={k:options[k] for k in ('temperature','num_ctx','num_predict')} for p in payloads)
    result=json.loads((output/'E-A/result.json').read_text())
    assert result['status']==('structured' if mode=='valid' else 'failed')
    assert 'unit' not in result and 'review_coverage' not in str(result) and not list(output.rglob('*.db'))
    raw=json.loads((output/'E-A/http_response.txt').read_text())
    assert raw['thinking']=='local thought' and raw['done_reason']==('length' if mode=='truncated' else 'stop')
    calls=[json.loads(line) for line in (output/'calls.jsonl').read_text().splitlines()]
    assert all(c['http_attempted'] and c['thinking_present'] and c['thinking_chars']==13 for c in calls)
    if mode=='valid':assert result['output']['evidence_refs'][0]['parse_run_id']=='p'
    with pytest.raises(FileExistsError):diagnostic.run_binding(args,freeze,package)
    assert len(payloads)==2
