"""Frozen Critic calls through the existing A2 contract; no revision generation."""
import argparse
import asyncio
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
from time import monotonic
from unittest.mock import patch


BINDING_PROMPT = '''제공 원문과 후보만 사용하여 요청된 관계의 유형 연결을 검수한다. 원명제의 끝점 대상이 선택 유형의 정의·조건·예외에 속하는지를 판단한다. 개념 동치가 필요한 것은 아니다. 업무 연관·소유·부분과 전체 관계만으로 유형 포함을 지지하지 않는다. 더 넓은 유형은 원명제의 좁은 한정이 보존되면 가능하며, 근거 없이 더 좁은 유형으로 대상 일부를 제외하면 부적합하다.
각 끝점의 실제 표현·조건과 선택 유형 정의를 대조하여 supported/refuted/unknown과 구체적인 이유를 각각 반환한다. 판정에 필요한 정의·한정이 실제 부족하면 unknown이다. 법정 정의 문구가 없다는 이유만으로 원문에 근거한 역할 추상화를 보류하지 않는다. 자료의 인접 조항은 서로 다른 정의일 수 있으므로 해당 대상의 구간을 대조한다.
relation_bindings는 검수 대상 선택이며 정답이 아니다. source_relation 없는 평가 조합에서는 endpoint_labels의 표현을 사용한다. 요청된 끝점만 판단하며 원명제 수정·누락 발굴·새 유형 설계·전체 의미 검수를 수행하지 않는다. JSON schema에 지정된 candidate_ref, binding_checks, binding_reasons, 실제 제공 source_refs만 반환한다. 이유는 각 400자 이내이며 원문과 유형 정의의 대응 또는 충돌을 설명한다.'''


def binding_schema(identifier, endpoints, source_refs):
    return dict(type='object',additionalProperties=False,required=['candidate_ref','binding_checks','binding_reasons','source_refs'],
        properties=dict(candidate_ref=dict(type='string',enum=[identifier]),
            binding_checks=dict(type='object',additionalProperties=False,required=endpoints,
                properties={k:dict(type='string',enum=['supported','refuted','unknown']) for k in endpoints}),
            binding_reasons=dict(type='object',additionalProperties=False,required=endpoints,
                properties={k:dict(type='string',minLength=1,maxLength=400) for k in endpoints}),
            source_refs=dict(type='array',minItems=1,uniqueItems=True,items=dict(type='string',enum=source_refs))))


def run_binding(args, frozen, package):
    import httpx
    import jsonschema
    from app.generation.service import GenerationService, local_ollama_url
    from app.knowledge import discovery_profile as profile, discovery_segments as segments
    from app.knowledge.service import utcnow
    from scripts.run_knowledge_a6 import write

    selected=frozen['settings'][args.setting]
    assert args.output.resolve()==Path(selected['output']).resolve()
    for path, expected in selected.get('prerequisites', {}).items():
        assert json.loads(Path(path).read_text(encoding='utf-8'))['passed'] is expected
    for path in selected.get('excluded_outputs', []): assert not Path(path).exists()
    generation=GenerationService();generation.ollama_url=local_ollama_url(frozen['endpoint'])
    with httpx.Client(timeout=30,trust_env=False) as client:
        tags=client.get(generation.ollama_url+'/api/tags');tags.raise_for_status()
        identity=next(m for m in tags.json()['models'] if m['name']==selected['model_options']['model'])
        assert identity['digest']==frozen['model_digest']
        show=client.post(generation.ollama_url+'/api/show',json=dict(model=identity['name']));show.raise_for_status()
        assert 'thinking' in show.json().get('capabilities', [])
    args.output.mkdir(parents=True,exist_ok=False)
    record=dict(started_at=utcnow(),setting=args.setting,mode='binding-only',
        code_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        freeze_sha256=sha256(args.freeze.read_bytes()).hexdigest(),model_identity=identity,
        participant_count=0,human_total_s=None,human_usefulness='unmeasured',cases=[])
    write(args.output/'started.json',record)
    calls=[];post=httpx.AsyncClient.post
    cases={c['id']:c for c in package['cases']}
    for identifier in selected['cases']:
        case=cases[identifier];case_path=args.output/identifier;case_path.mkdir()
        prompt,schema=case['prompt'],case['schema']
        assert sha256(prompt.encode()).hexdigest()==case['prompt_sha256']
        assert profile.digest(schema)==case['schema_sha256']
        assert len(prompt)<=frozen['input_chars']
        left=selected['model_seconds']-sum(c['elapsed_s'] for c in calls)
        if len(calls)>=selected['http_calls'] or left<=0: raise ValueError('고정 진단 예산 종료')
        timeout=min(frozen['http_timeout_s'],left)
        row=dict(case=identifier,elapsed_s=0,http_attempted=False,prompt_sha256=case['prompt_sha256'],schema_sha256=case['schema_sha256'])
        result=dict(case=identifier,status='failed');calls.append(row)
        async def observed_post(client,url,**kwargs):
            if str(url).endswith('/api/generate'):
                if row['http_attempted']: raise ValueError('진단별 실제 HTTP 1회 한도')
                payload=kwargs['json'];options=selected['model_options']
                assert payload['model']==options['model'] and payload['think'] is options['think'] and payload['stream'] is False
                assert payload['options']=={k:options[k] for k in ('temperature','num_ctx','num_predict')}
                assert payload['prompt']==prompt and payload['format']==schema
                row.update(http_attempted=True,http_options={k:payload[k] for k in ('model','think','options','stream')})
            response=await post(client,url,**kwargs)
            (case_path/'http_response.txt').write_bytes(response.content)
            row['http_status']=response.status_code
            try:
                raw=response.json()
                row.update(thinking_present='thinking' in raw,thinking_chars=len(raw.get('thinking') or ''),
                    response_present='response' in raw,response_chars=len(raw.get('response') or ''),
                    metadata={k:raw.get(k) for k in ('done','done_reason','prompt_eval_count','eval_count','total_duration')})
            except ValueError: pass
            return response
        tick=monotonic()
        try:
            async def generate():
                return await asyncio.wait_for(generation.call_ollama(prompt,response_schema=schema,
                    **selected['model_options'],timeout=timeout,return_metadata=True,local_only=True),timeout)
            with patch.object(httpx.AsyncClient,'post',observed_post): response=asyncio.run(generate())
            result['response']=response
            assert response['done'] and response['done_reason']=='stop', '출력 잘림 또는 미완료'
            assert response['prompt_eval_count']<=selected['model_options']['num_ctx']-selected['model_options']['num_predict'], '입력 토큰 한도'
            output=json.loads(response['text']);jsonschema.validate(output,schema)
            assert all(reason.strip() for reason in output['binding_reasons'].values()), '빈 연결 사유'
            segments.restore(output,{b['id']:b for b in package['blocks']},case['source_views'])
            result.update(status='structured',output=output,semantic_status='independent_review_required')
        except Exception as exc: result['error']=str(exc)
        finally:
            row['elapsed_s']=round(monotonic()-tick,3)
            with (args.output/'calls.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
            result.update(http_calls=int(row['http_attempted']),model_total_s=row['elapsed_s'])
            write(case_path/'result.json',result)
            record['cases'].append(dict(case=identifier,status=result['status'],result_sha256=sha256((case_path/'result.json').read_bytes()).hexdigest()))
    record.update(finished_at=utcnow(),http_calls=sum(c['http_attempted'] for c in calls),model_total_s=round(sum(c['elapsed_s'] for c in calls),3),
        original_files_unchanged=all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in frozen['original_hashes'].items()),
        code_unchanged=all(sha256(Path(p).read_bytes()).hexdigest()==h for p,h in frozen['runtime_hashes'].items()))
    write(args.output/'result.json',record)
    print(json.dumps(record,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--setting')
    args=parser.parse_args()
    import httpx
    from app.knowledge import discovery_analysis as a2, discovery_synthesis as synthesis, discovery_profile as profile
    from app.knowledge.service import KnowledgeService, utcnow
    from app.generation.service import GenerationService
    from scripts.run_knowledge_a6 import write

    def digest(path): return sha256(Path(path).read_bytes()).hexdigest()

    frozen=json.loads(args.freeze.read_text(encoding='utf-8'))
    inputs=frozen['diagnostic_inputs']
    assert digest(inputs['path'])==inputs['sha256']
    package=json.loads(Path(inputs['path']).read_text(encoding='utf-8'))
    assert all(digest(p)==h for p,h in frozen['runtime_hashes'].items())
    assert digest(__file__)==frozen['diagnostic_runner']['sha256']
    assert all(digest(p)==h for p,h in frozen['original_hashes'].items())
    if frozen.get('diagnostic_mode')=='binding-only':
        run_binding(args,frozen,package)
        return
    if args.setting:
        from app.core.config import settings
        selected=frozen['settings'][args.setting]
        settings.KNOWLEDGE_DISCOVERY_REVIEW_MODEL=selected['model']
        package['run']['recipe']=deepcopy(selected['recipe'])
    else: selected=dict(model_options=frozen['model_options'],model_digests=frozen['model_digests'],http_calls=2,model_seconds=600)
    identity=a2.model_identity(package['run']['recipe'])
    package['run']['model_identity']=identity
    assert {k:v['digest'] for k,v in identity.items()}==selected['model_digests']
    assert all(digest(p)==h for p,h in frozen['original_hashes'].items())
    args.output.mkdir(parents=True,exist_ok=False)
    record=dict(started_at=utcnow(),code_sha=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        setting=args.setting,freeze_sha256=digest(args.freeze),runtime_hashes=frozen['runtime_hashes'],model_identity=identity,cases=[],
        participant_count=0,human_total_s=None,human_usefulness='unmeasured')
    write(args.output/'started.json',record)
    calls=[]; original=GenerationService.call_ollama;post=httpx.AsyncClient.post
    for case in package['cases']:
        case_path=args.output/case['id'];case_path.mkdir()
        with sqlite3.connect(Path(package['source_db']).resolve().as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(case_path/'knowledge.db') as target:
            source.backup(target)
        service=KnowledgeService(case_path/'knowledge.db');run=deepcopy(package['run']);group=deepcopy(case['group'])
        case_calls=[]
        async def observed_post(client,url,**kwargs):
            if str(url).endswith('/api/generate'):
                if case_calls[-1].get('http_attempted'): raise ValueError('진단별 실제 HTTP 1회 한도')
                case_calls[-1]['http_attempted']=True
                payload=kwargs['json'];case_calls[-1]['http_options']={k:payload.get(k) for k in ('model','options','think','stream')}
            return await post(client,url,**kwargs)
        async def measured(instance,prompt,**kwargs):
            left=selected['model_seconds']-sum(c['elapsed_s'] for c in calls)
            if case_calls or len(calls)>=selected['http_calls'] or left<=0: raise ValueError('고정 진단 예산 종료')
            assert sha256(prompt.encode()).hexdigest()==case['prompt_sha256']
            assert profile.digest(kwargs['response_schema'])==case['schema_sha256']
            assert all(kwargs[k]==v for k,v in selected['model_options'].items() if k!='timeout')
            kwargs['timeout']=min(300,left,kwargs.get('timeout') or 300)
            row=dict(case=case['id'],elapsed_s=0,prompt_sha256=case['prompt_sha256'],
                schema_sha256=profile.digest(kwargs['response_schema']),
                options={k:v for k,v in kwargs.items() if k in {'model','num_ctx','num_predict','think','temperature','timeout'}})
            case_calls.append(row);calls.append(row);tick=monotonic()
            try:
                result=await asyncio.wait_for(original(instance,prompt,**kwargs),kwargs['timeout'])
                row['metadata']={k:v for k,v in result.items() if k!='text'}
                return result
            except Exception as exc: row['error']=str(exc);raise
            finally:
                row['elapsed_s']=round(monotonic()-tick,3)
                with (args.output/'calls.jsonl').open('a',encoding='utf-8') as stream:stream.write(json.dumps(row,ensure_ascii=False)+'\n')
        try:
            by_id={b['id']:b for b in a2.load_blocks(service,run)}
            with patch.object(GenerationService,'call_ollama',measured),patch.object(httpx.AsyncClient,'post',observed_post):
                output=a2.call(service,run,'critic',case.get('key',group['id']),case['context'],case['deps'],by_id,case['supplied'])
            if output is not None:
                a2.queue_recovery(run,output,group,by_id)
                # The frozen diagnostic has revisions=0: expose requested targets, never generate a repair.
                candidate_revision=bool(group.get('source_errors')) or output['needs_revision'] and (not output.get('missing_meanings') or any(i.get('candidate_ref') for i in output['issues']))
                if candidate_revision or any(c['judgment']!='supported' for field in ('relation_checks','observation_checks') for c in output.get(field, [])) or any(c.get('evidence_validation') for c in case['supplied'].values()):
                    synthesis.revise(service,run,group,output,package['taxonomy'],by_id,profile.contexts(list(by_id.values())))
            unit=run['analysis_units'][-1]
            result=dict(case=case['id'],unit=unit,recovery_requests=run.get('recovery_requests',[]),
                revision_targets=group.get('revision_deferrals',[]),http_calls=sum(c.get('http_attempted',False) for c in case_calls),
                model_total_s=round(sum(c['elapsed_s'] for c in case_calls),3))
            write(case_path/'result.json',result);record['cases'].append(dict(case=case['id'],status=unit['status'],result_sha256=digest(case_path/'result.json')))
        finally: service.shutdown()
    record.update(finished_at=utcnow(),http_calls=sum(c.get('http_attempted',False) for c in calls),
        model_total_s=round(sum(c['elapsed_s'] for c in calls),3),
        original_files_unchanged=all(digest(p)==h for p,h in frozen['original_hashes'].items()),
        code_unchanged=all(digest(p)==h for p,h in frozen['runtime_hashes'].items()))
    write(args.output/'result.json',record)
    print(json.dumps(record,ensure_ascii=False))


if __name__=='__main__':main()
