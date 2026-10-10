"""Frozen direct source-ID selection and independent physical-structure comparison."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import time
import urllib.request

import business_direct_source_inputs as adapter

selection,prior=adapter.selection,adapter.prior
ROOT,read,write,sha=adapter.ROOT,adapter.read,adapter.write,adapter.sha
OUT=ROOT/'data/knowledge/evaluations/business_direct_selection_structure_20261010'
IDS=['c47','c13','c46','K02','AR01','AR02','AR03']
DB=Path('/Users/hyeongi/.codex/worktrees/business-requirement-answer-flow/Civil-Complaints-System/data/knowledge/evaluations/business_requirement_answer_flow_20261009/reason_boundary_live/knowledge.db')


def prepare():
    assert not (OUT/'prepared.json').exists()
    OUT.mkdir(exist_ok=True)
    adapter.selfcheck()
    selection.check_prepared()
    old={c['id']:c for c in read(prior.OUT/'inputs.json')+read(selection.confirmation.OUT/'inputs.json')}
    cases=[old[i] for i in IDS]
    connection=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True)
    connection.execute('PRAGMA query_only=ON')
    run=json.loads(connection.execute('select payload from runs where id=?',('cedacf0841e540cf83934db6d821140c',)).fetchone()[0])
    originals={}
    for case in cases:
        originals[case['id']]={}
        for block in case['blocks']:
            if case['id'].startswith('c'):
                original=run['blocks'][int(block['id'][1:])-1]
                assert original['text']==block['text']
            else:
                # Content-addressed research projection, explicitly not a stored product parser block.
                namespace=prior.text_hash(json.dumps(case.get('source'),sort_keys=True,ensure_ascii=False)+block['text'])
                original=dict(id='research:'+namespace+':'+block['id'],text=block['text'],
                              source_version_id='research-text-sha256:'+prior.text_hash(block['text']),
                              parse_run_id=None,locator=dict(kind='saved_research_text_projection',source=case.get('source')))
            originals[case['id']][block['id']]=original
    connection.close()
    audit=adapter.arko_structure(selection.confirmation.OUT)
    structure=adapter.compact_structure(audit)
    provided={c['id']:adapter.views(c,originals[c['id']]) for c in cases}
    baselines={r['id']:r for r in read(prior.OUT/'baselines.json')}
    saved=[]
    for ident in IDS[:4]:
        row=baselines[ident]
        assert row['prompt']==prior.previous.prompt(old[ident]) and sha(ROOT/row['raw_path'])==row['raw_sha256']
        saved.append(row)
    old_criteria=read(prior.OUT/'criteria.json')
    criteria=dict(issues=[643,644],expected={'c47':'U','c13':'S','c46':'S','K02':'U','AR01':'S','AR02':'S','AR03':'U'},
                  rubric={i:old_criteria['reason_rubric'][i] for i in IDS[:4]},
                  ar_review=read(selection.confirmation.OUT/'criteria.json')['review'],
                  gates=['Address success is separate from semantic success.',
                         'Read actual evidence, candidate error span, reason, source_state and U/C distinction.',
                         'A requires c47 scope detection and both normal cases preserved; K02 modality control.',
                         'B compares new plain and structured arms only, with identical source/candidate/selection/settings.',
                         'B runs independently of A meaning. All failures remain denominator; no retries or corrected selections.',
                         'All cases development-exposed. No general performance claim or automatic product adoption.'])
    rows=[dict(id=c['id'],task='select',prompt=adapter.selector_prompt(c,provided[c['id']])) for c in cases]
    write(OUT/'inputs.json',cases);write(OUT/'originals.json',originals);write(OUT/'provided.json',provided)
    write(OUT/'physical_structure_audit.json',audit);write(OUT/'physical_structure.json',structure)
    write(OUT/'saved_baselines.json',saved);write(OUT/'criteria.json',criteria);write(OUT/'prompts.json',rows)
    (OUT/'settings.json').write_bytes((prior.OUT/'settings.json').read_bytes())
    write(OUT/'provenance.json',dict(database=str(DB),database_sha256=sha(DB),parent_run_id=run['id'],
          source_versions=run['sources'],busan_original_html='not present in copied evaluation DB; stored parser locator verified',
          ar_files={str(p.relative_to(ROOT)):sha(p) for p in [selection.confirmation.OUT/n for n in
                    ['source.html','general_section.html','source.txt','table_structure.json']]},
          structure_loss='HTML parser records DOM; storage preserves locator. source_packet filters element_path but list_parents is separately delivered for Busan. AR research preparation flattened HTML into one text block.',
          selection_unit='Unchanged old newline segments, now whole lines selected by ID. c47 repeated phrases within one line are not individually selected.',
          ar_projection='Research text version and null parse_run_id are not product parser identities.',
          pair_invariant='Full case, selected spans and instruction identical; only physical_structure property added. First two context lines kept without invented DOM.'))
    code={**read(selection.OUT/'prepared.json')['code'],**{str(p.relative_to(ROOT)):sha(p) for p in
         [Path(__file__),ROOT/'scripts/business_direct_source_inputs.py',ROOT/'app/knowledge/discovery_segments.py']}}
    write(OUT/'prepared.json',dict(at=time.time(),code=code,files={p.name:sha(p) for p in OUT.iterdir() if p.is_file()},
          max_calls=17,order='seven direct selectors, seven plain judges, three AR structured judges; no retries'))
    print(OUT,flush=True)


def check():
    selection.check_prepared()
    frozen=read(OUT/'prepared.json')
    assert all(sha(ROOT/n)==h for n,h in frozen['code'].items())
    assert all(sha(OUT/n)==h for n,h in frozen['files'].items())
    assert sha(DB)==read(OUT/'provenance.json')['database_sha256']


def preflight():
    assert not (OUT/'freeze.json').exists()
    check()
    assert read(OUT/'execution_authorization.json')['compute_allocated']
    identity=read(prior.previous.OUT/'runtime_identity.json')
    for key in ['engine','gguf']: assert sha(Path(identity[key+'_path']))==identity[key+'_sha256']
    with urllib.request.urlopen('http://127.0.0.1:11434/api/ps',timeout=10) as stream: assert not json.load(stream)['models']
    props=prior.previous.prior.base.api('/props');old=read(prior.OUT/'props.json')
    assert {k:v for k,v in props.items() if k!='media_marker'}=={k:v for k,v in old.items() if k!='media_marker'}
    rows=[prior.request_row(r) for r in read(OUT/'prompts.json')]
    # Check source-only judge context; an oversized all-lines diagnostic does not authorize truncation.
    maximum=[]
    for c in read(OUT/'inputs.json'):
        provided=read(OUT/'provided.json')[c['id']]
        parsed=adapter.restore(dict(source_refs=[v['source_ref'] for v in provided]),c,read(OUT/'originals.json')[c['id']],provided)
        for task in (['plain','structured'] if c['id'].startswith('AR') else ['plain']):
            structure=read(OUT/'physical_structure.json') if task=='structured' else None
            base=prior.request_row(dict(id=c['id'],task=task,prompt=adapter.judgment_prompt(c,[],structure)))
            diagnostic=dict(id=c['id'],task=task,source_only_tokens=base['input_tokens'])
            try:
                row=prior.request_row(dict(id=c['id'],task=task,prompt=adapter.judgment_prompt(c,parsed['selected_source_spans'],structure)))
                diagnostic['all_lines_tokens']=row['input_tokens']
            except ValueError as error: diagnostic['all_lines_error']=repr(error)
            maximum.append(diagnostic)
    write(OUT/'requests.json',rows);write(OUT/'props.json',props);write(OUT/'context_check.json',maximum)
    write(OUT/'freeze.json',dict(at=time.time(),max_calls=17,files={n:sha(OUT/n) for n in
          ['prepared.json','requests.json','props.json','context_check.json','execution_authorization.json']}))


def run():
    check()
    assert all(sha(OUT/n)==h for n,h in read(OUT/'freeze.json')['files'].items())
    assert prior.previous.prior.base.api('/props')==read(OUT/'props.json')
    dest=OUT/'run';dest.mkdir()
    cases={c['id']:c for c in read(OUT/'inputs.json')}
    provided=read(OUT/'provided.json');originals=read(OUT/'originals.json')
    result=dict(calls=0,records=[],semantic_review='pending');start=time.monotonic()
    def save():
        result['wall_s']=time.monotonic()-start;write(dest/'result.json',result)
    def call(row):
        record=dict(id=row['id'],task=row['task'],input_tokens=row['input_tokens'],contract_pass=False,
                    request_sha256=prior.text_hash(json.dumps(row['request'],ensure_ascii=False)))
        result['records'].append(record);result['calls']+=1;assert result['calls']<=17;save()
        before=time.monotonic()
        try:
            raw=prior.previous.prior.base.call('/completion',row['request'])
            path=dest/(row['id']+'_'+row['task']+'_response.json');path.write_bytes(raw)
            response=json.loads(raw)
            record.update(raw_sha256=sha(path),timings=response.get('timings'),stop_type=response.get('stop_type'),truncated=response.get('truncated'))
            if response.get('stop_type')!='eos' or response.get('truncated'): raise ValueError('incomplete_generation')
            answer=json.loads('{'+response['content'],object_pairs_hook=prior.previous.strict_object)
            record['answer']=answer
            if row['task']=='select':
                record['parsed']=adapter.restore(answer,cases[row['id']],originals[row['id']],provided[row['id']])
            else:
                record['parsed']=prior.previous.parse_final(answer,cases[row['id']])
                record['label']=prior.previous.prior.MAPPING[answer['label']]
            record['contract_pass']=True
        except (OSError,ValueError,KeyError,TypeError) as error: record['error']=repr(error)
        record['elapsed_s']=time.monotonic()-before;save()
        print(row['id'],row['task'],record['contract_pass'],record.get('label'),record.get('error'),flush=True)
        return record
    for row in read(OUT/'requests.json'): call(row)
    dynamic=[]
    for task in ['plain','structured']:
        for record in [r for r in result['records'] if r['task']=='select' and r['contract_pass']]:
            ident=record['id']
            if task=='structured' and not ident.startswith('AR'):continue
            spans=record['parsed']['selected_source_spans']
            try:
                row=prior.request_row(dict(id=ident,task=task,prompt=adapter.judgment_prompt(cases[ident],spans,read(OUT/'physical_structure.json') if task=='structured' else None)))
            except ValueError as error:
                result['records'].append(dict(id=ident,task=task,contract_pass=False,called=False,error=repr(error)))
                save();continue
            dynamic.append(dict(row,selection_raw_sha256=record['raw_sha256'],selected_source_spans=spans))
            write(dest/'judgment_requests.json',dynamic)
            call(row)
    save()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','preflight','run','check'])
    globals()[parser.parse_args().mode]()
