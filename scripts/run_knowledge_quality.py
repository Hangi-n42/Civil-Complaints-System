"""Small real-model comparison on a read-only copy of frozen A1 inputs; no decisions."""
import argparse
import asyncio
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from time import monotonic
from unittest.mock import patch


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--code-root', type=Path, required=True)
    parser.add_argument('--study', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args()
    sys.path.insert(0,str(args.code_root.resolve()))
    import httpx
    from app.knowledge import discovery_analysis as a2, ontology_changes as changes, ontology_schema
    from app.knowledge.service import KnowledgeService, utcnow
    from app.knowledge.schemas import RunRequest
    from app.generation.service import GenerationService
    from scripts.run_knowledge_a6 import write, wait, digest

    config=json.loads(args.config.read_text(encoding='utf-8'))
    case=next(c for c in config['cases'] if c['id']==args.case)
    original=json.loads((args.study/(case['source_case']+'.json')).read_text(encoding='utf-8'))
    identity=a2.model_identity(a2.recipe(config['budgets']))
    if {k:v['digest'] for k,v in identity.items()}!=config['model_digests']:
        raise ValueError('고정 모델 digest 불일치')
    source_db=args.study/'knowledge.db'; source_hash=digest(source_db)
    if source_hash!=config['source_db_sha256']: raise ValueError('원본 원장 해시 불일치')
    args.output.mkdir(parents=True,exist_ok=False)
    code_files=sorted((args.code_root/'app/knowledge').glob('*.py'))+[args.code_root/'app/generation/service.py']
    record=dict(case=case, config_sha256=digest(args.config), started_at=utcnow(), model_identity=identity,
        code_sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.code_root,text=True).strip(),
        code_hashes={str(p.relative_to(args.code_root)):digest(p) for p in code_files},
        participant_count=0,human_total_s=None,model_calls=[])
    write(args.output/'started.json',record)
    db_path=args.output/'knowledge.db'
    with sqlite3.connect(source_db.resolve().as_uri()+'?mode=ro',uri=True) as source, sqlite3.connect(db_path) as target:
        source.backup(target)
    service=KnowledgeService(db_path)
    calls=record['model_calls']; call=GenerationService.call_ollama; post=httpx.AsyncClient.post
    async def observed_post(client,url,**kwargs):
        if str(url).endswith('/api/generate'): calls[-1]['http_attempted']=True
        return await post(client,url,**kwargs)
    async def measured(instance,prompt,**kwargs):
        left=config['budgets']['model_seconds']-sum(c['elapsed_s'] for c in calls)
        if len(calls)>=config['budgets']['model_calls'] or left<=0: raise ValueError('고정 모델 예산 종료')
        kwargs['timeout']=min(left,config['call_timeout_s'],kwargs.get('timeout') or config['call_timeout_s'])
        row=dict(prompt_sha256=sha256(prompt.encode()).hexdigest(),prompt_chars=len(prompt),elapsed_s=0,
                 options={k:v for k,v in kwargs.items() if k in {'model','num_ctx','num_predict','think','temperature','timeout'}})
        calls.append(row); tick=monotonic()
        try:
            result=await asyncio.wait_for(call(instance,prompt,**kwargs),kwargs['timeout'])
            row['metadata']={k:v for k,v in result.items() if k!='text'}
            return result
        except Exception as exc:
            row['error']=str(exc);raise
        finally:
            row['elapsed_s']=round(monotonic()-tick,3)
            with (args.output/'calls.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(row,ensure_ascii=False)+'\n')
    tick=monotonic()
    try:
        with ExitStack() as stack:
            stack.enter_context(patch.object(GenerationService,'call_ollama',measured))
            stack.enter_context(patch.object(httpx.AsyncClient,'post',observed_post))
            grounded=original['input_run']; blocks=a2.load_blocks(service,grounded)
            selected=[b['id'] for b in blocks if b['file_id'] in case['analysis_file_ids']]
            record['input_run_id']=grounded['id']
            record['input_blocks']=[dict(id=b['id'],file_id=b['file_id'],text_sha256=sha256(b['text'].encode()).hexdigest(),locator=b['locator']) for b in blocks]
            request=RunRequest(kind='discovery',discovery_mode='analyze',input_run_id=grounded['id'],
                base_ontology_version_id=original['run'].get('base_ontology_version_id'),
                lineage_id=original['run']['lineage_id'], cqs=case['cqs'],
                analysis_block_ids=selected,analysis_selection_reason=case['selection_reason'],discovery_budgets=config['budgets'])
            run=wait(service,service.start(request)['run_id']);record['run']=run
            record['changeset_id']=changes.publish(service,run['id'])['changeset_id']
            record['candidates']=ontology_schema.candidates(service,record['changeset_id'])
    except Exception as exc: record['error']=str(exc)
    finally:
        service.shutdown()
        record.update(finished_at=utcnow(),elapsed_s=round(monotonic()-tick,3),
            model_total_s=round(sum(c['elapsed_s'] for c in calls),3),http_calls=sum(c.get('http_attempted',False) for c in calls),
            source_db_unchanged=digest(source_db)==source_hash,
            execution_code_unchanged=all(digest(args.code_root/name)==expected for name,expected in record['code_hashes'].items()))
        write(args.output/'result.json',record)
    print(json.dumps({k:record.get(k) for k in ('case','error','http_calls','model_total_s','elapsed_s','source_db_unchanged','execution_code_unchanged')},ensure_ascii=False))


if __name__=='__main__': main()
