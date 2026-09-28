"""Replay one frozen K4 pilot with the current recipe; retain original model output."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import settings
from app.knowledge import extraction, extraction_store
from app.knowledge.service import KnowledgeService, encode


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-run',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with sqlite3.connect(f'file:{settings.KNOWLEDGE_DB_PATH}?mode=ro',uri=True) as db:
        if any(json.loads(row[0])['status'] in {'queued','running','cancel_requested'} for row in db.execute('SELECT payload FROM runs')):
            raise RuntimeError('실행 중인 작업이 있습니다.')
        baseline=json.loads(db.execute('SELECT payload FROM runs WHERE id=?',(args.baseline_run,)).fetchone()[0])
    service=KnowledgeService(settings.KNOWLEDGE_DB_PATH)
    try:
        run=deepcopy(baseline)
        for key in ('changeset_id','previous_metrics','reused_units','invalid_record_count'):
            run.pop(key,None)
        identifier=uuid4().hex
        selected={b for u in baseline['units'] for b in u['block_ids']}
        run.update(id=identifier,data_run_id=identifier,recipe=extraction.recipe(),status='queued',retry_of_run_id=None,
                   started_at=None,finished_at=None,units=extraction.plan_units([b for b in run['frozen_blocks'] if b['id'] in selected]),
                   metrics=dict(llm_calls=0,model_total_s=0,elapsed_s=0))
        run['planned_llm_calls']=sum(u['stage']=='llm' for u in run['units'])
        with service.repository.connect() as db:db.execute('INSERT INTO runs VALUES(?,?)',(identifier,encode(run)))
        extraction.execute(service,identifier)
        completed=service.run(identifier)
        result=extraction_store.candidates(service,completed['changeset_id']) if completed.get('changeset_id') else {'items':[]}
        report=dict(baseline_run=baseline['id'],run_id=identifier,status=completed['status'],metrics=completed['metrics'],
                    baseline_metrics=baseline['metrics'],planned_llm_calls=completed['planned_llm_calls'],
                    same_frozen_blocks=completed['frozen_blocks']==baseline['frozen_blocks'],
                    same_aliases=completed['accepted_aliases']==baseline['accepted_aliases'],
                    units=[{k:u.get(k) for k in ('id','stage','status','error','call','coverage','records','invalid_records')} for u in completed['units']],
                    candidates=result['items'])
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:report[k] for k in ('run_id','status','metrics','same_frozen_blocks','same_aliases')},ensure_ascii=False))
    finally:service.shutdown()


if __name__=='__main__':main()
