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


from app.knowledge.discovery_binding import PROMPT as BINDING_PROMPT, schema as binding_schema


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
                expected=case_calls[-1]['options']
                assert payload['model']==expected['model'] and payload['think'] is expected['think'] and payload['stream'] is False
                assert payload['options']=={k:expected[k] for k in ('temperature','num_ctx','num_predict')}
            return await post(client,url,**kwargs)
        async def measured(instance,prompt,**kwargs):
            left=selected['model_seconds']-sum(c['elapsed_s'] for c in calls)
            components=case.get('components',[case])
            if len(case_calls)>=len(components) or len(calls)>=selected['http_calls'] or left<=0: raise ValueError('고정 진단 예산 종료')
            expected=components[len(case_calls)]
            assert sha256(prompt.encode()).hexdigest()==expected['prompt_sha256']
            assert profile.digest(kwargs['response_schema'])==expected['schema_sha256']
            assert all(kwargs[k]==v for k,v in expected.get('model_options',selected['model_options']).items() if k!='timeout')
            kwargs['timeout']=min(300,left,kwargs.get('timeout') or 300)
            row=dict(case=case['id'],component=expected.get('component'),elapsed_s=0,prompt_sha256=expected['prompt_sha256'],
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
                if case.get('split_review'):
                    output=synthesis.focused_reviews(service,run,group,case['context'],case['deps'],case['supplied'],
                        by_id,profile.contexts(list(by_id.values())),blocks=list(by_id.values()))
                else:
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
            if case.get('split_review'):
                result.update(units=run['analysis_units'],review=output,review_unit_ids=group['review_unit_ids'])
                result['status']='succeeded' if output is not None and not output.get('record_errors') and not output['review_coverage']['pending_candidate_ids'] else 'partial'
            write(case_path/'result.json',result);record['cases'].append(dict(case=case['id'],status=result.get('status',unit['status']),result_sha256=digest(case_path/'result.json')))
        finally: service.shutdown()
    record.update(finished_at=utcnow(),http_calls=sum(c.get('http_attempted',False) for c in calls),
        model_total_s=round(sum(c['elapsed_s'] for c in calls),3),
        original_files_unchanged=all(digest(p)==h for p,h in frozen['original_hashes'].items()),
        code_unchanged=all(digest(p)==h for p,h in frozen['runtime_hashes'].items()))
    write(args.output/'result.json',record)
    print(json.dumps(record,ensure_ascii=False))


if __name__=='__main__':main()
