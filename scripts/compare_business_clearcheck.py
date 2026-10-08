"""One frozen ClearCheck CoT diagnostic on original Korean inputs; no product writes."""
import argparse
import ast
import importlib.metadata
import json
from pathlib import Path
import re
import time

from compare_business_nli import read, write, sha

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/knowledge/evaluations/business_nli_20261009'
OUT=ROOT/'data/knowledge/evaluations/business_clearcheck_20261009'
MODEL='just1nseo/ClearCheck-8B'
REVISION='89255c69f65d49e574092772963afc3e5ba6a30b'
LABELS=['Attributable','Not Attributable','Contradictory']


def official_template(path):
    """Read only constant/template AST nodes, without importing the upstream package."""
    names={}
    for node in ast.parse(path.read_text(encoding='utf-8')).body:
        if not isinstance(node,ast.Assign) or len(node.targets)!=1 or not isinstance(node.targets[0],ast.Name): continue
        name=node.targets[0].id
        if name in {'DOCUMENT_PLACEHOLDER','STATEMENT_PLACEHOLDER'}:
            names[name]=ast.literal_eval(node.value)
        if name=='CLEARCHECK_COT':
            parts=[]
            for item in node.value.values:
                if isinstance(item,ast.Constant): parts.append(item.value)
                elif isinstance(item,ast.FormattedValue) and isinstance(item.value,ast.Name): parts.append(names[item.value.id])
                else: raise ValueError('unexpected_template_expression')
            return ''.join(parts),names
    raise ValueError('missing_official_template')


def label_from_raw(raw):
    brackets=re.findall(r'\[.*?\]',raw,flags=re.DOTALL)
    final=re.sub(r'[^\w\s]','',brackets[-1][1:-1]).strip().casefold() if brackets else ''
    return next((label for label in LABELS if label.casefold()==final),None)


def freeze():
    from transformers import AutoTokenizer
    assert not (OUT/'freeze.json').exists()
    folder=Path(read(OUT/'download.json')['path']);assert folder.name==REVISION
    tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True,trust_remote_code=False)
    template,names=official_template(OUT/'reference_data_templates.py')
    originals=read(BASE/'inputs.json');packet=read(BASE/'source_packet.json')
    assert all(x['premise']=='\n'.join(b['text'] for b in packet['blocks']) for x in originals)
    inputs=[]
    for p in originals:
        prompt=template.replace(names['STATEMENT_PLACEHOLDER'],p['hypothesis']).replace(names['DOCUMENT_PLACEHOLDER'],p['premise'])
        messages=[dict(role='user',content=prompt)]
        formatted=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
        ids=tokenizer(formatted,add_special_tokens=False,truncation=False)['input_ids']
        assert ids==tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True)
        inputs.append(dict(id=p['id'],messages=messages,formatted=formatted,input_ids=ids,input_tokens=len(ids)))
    write(OUT/'inputs.json',inputs)
    write(OUT/'criteria.json',dict(expected=dict(c13=LABELS[0],c46=LABELS[0],c47=LABELS[1],c11=LABELS[0]),
        gate='All four exact 3-way labels and source-faithful reasons; exposed development cases, no stability claim.',
        failures='Truncation, missing labels and execution failures remain unresolved in denominator; no binary merge.',
        downstream='Only if development gate and separate reason review pass.'))
    write(OUT/'freeze.json',dict(model=MODEL,revision=REVISION,variant='Official ClearCheck CoT prompt with Transformers/MPS runtime',
        reference_revision=read(OUT/'reference_metadata.json')['github_revision'],template=template,
        chat_template=tokenizer.chat_template,device='mps',dtype='bfloat16',attention='sdpa',context_limit=32768,
        generation=dict(do_sample=True,temperature=0.1,top_p=1.0,top_k=0,max_new_tokens=1024,
            repetition_penalty=1.0,num_return_sequences=1,eos_token_id=[128001,128008,128009],pad_token_id=tokenizer.pad_token_id),
        seed=42,max_calls=4,truncation=False,logprobs='Native pre-sampling logits converted to top-3 log probabilities and selected-token log probability; engine differs from vLLM.',
        checkpoint={str(p):sha(p) for p in folder.iterdir() if p.is_file()},
        files={str(p.relative_to(ROOT)):sha(p) for p in [OUT/'inputs.json',OUT/'criteria.json',OUT/'reference_data_templates.py',
            OUT/'reference_models_attributor.py',BASE/'inputs.json',BASE/'source_packet.json',Path(__file__),ROOT/'scripts/compare_business_nli.py']},
        versions={n:importlib.metadata.version(n) for n in ['torch','transformers','accelerate','safetensors','huggingface-hub','tokenizers']}))


def run():
    import torch
    from transformers import AutoModelForCausalLM,AutoTokenizer,set_seed
    f=read(OUT/'freeze.json'); inputs=read(OUT/'inputs.json')
    assert all(sha(ROOT/p)==v for p,v in f['files'].items())
    assert all(sha(Path(p))==v for p,v in f['checkpoint'].items())
    assert not (OUT/'started.json').exists(), 'Single frozen run only'
    write(OUT/'started.json',dict(freeze_sha256=sha(OUT/'freeze.json')))
    result=dict(model=MODEL,revision=REVISION,cases=[],calls=0,gate_passed=False)
    folder=Path(read(OUT/'download.json')['path'])
    try:
        set_seed(f['seed']);started=time.monotonic()
        tokenizer=AutoTokenizer.from_pretrained(folder,local_files_only=True,trust_remote_code=False)
        model=AutoModelForCausalLM.from_pretrained(folder,torch_dtype=torch.bfloat16,device_map={'':'mps'},
            low_cpu_mem_usage=True,local_files_only=True,trust_remote_code=False,use_safetensors=True,attn_implementation='sdpa').eval()
        torch.mps.synchronize();result['load_s']=time.monotonic()-started
        result['actual_parameters']=sorted({(str(p.device),str(p.dtype)) for p in model.parameters()})
        result['actual_attention']=model.config._attn_implementation
        write(OUT/'result.json',result)
        for p in inputs:
            record=dict(id=p['id'],status='pending',predicted=None,input_tokens=p['input_tokens'])
            result['cases'].append(record)
            if p['input_tokens']+f['generation']['max_new_tokens']>f['context_limit']:
                record['status']='input_capacity';continue
            encoded=torch.tensor([p['input_ids']],device='mps')
            result['calls']+=1;write(OUT/'result.json',result)
            torch.mps.synchronize();started=time.monotonic()
            with torch.inference_mode():
                output=model.generate(input_ids=encoded,attention_mask=torch.ones_like(encoded),**f['generation'],
                    return_dict_in_generate=True,output_logits=True,use_cache=True)
            torch.mps.synchronize();record['elapsed_s']=time.monotonic()-started
            ids=output.sequences[0,p['input_tokens']:].tolist()
            raw=tokenizer.decode(ids,skip_special_tokens=True)
            stop='eos' if ids and ids[-1] in f['generation']['eos_token_id'] else 'length' if len(ids)>=f['generation']['max_new_tokens'] else 'other'
            logprobs=[]
            for token,logits in zip(ids,output.logits):
                lp=torch.log_softmax(logits[0].detach().float().cpu(),dim=-1)
                values,indices=lp.topk(3)
                logprobs.append(dict(token_id=token,logprob=lp[token].item(),top3_ids=indices.tolist(),top3_logprobs=values.tolist()))
            predicted=label_from_raw(raw)
            record.update(raw=raw,generated_token_ids=ids,output_tokens=len(ids),stop_reason=stop,raw_label=predicted,
                predicted=predicted if stop=='eos' else None,status='succeeded' if stop=='eos' and predicted else 'unresolved',
                token_logprobs=logprobs,mps_allocated_bytes=torch.mps.current_allocated_memory(),mps_driver_bytes=torch.mps.driver_allocated_memory())
            write(OUT/'result.json',result)
            print(p['id'],record['status'],record['predicted'],len(ids),record['elapsed_s'],flush=True)
            del output,encoded;torch.mps.empty_cache()
        expected=read(OUT/'criteria.json')['expected']
        result['label_gate_passed']=len(result['cases'])==len(expected) and all(c['predicted']==expected[c['id']] for c in result['cases'])
        result['semantic_gate']='Requires separate review of raw reasons; no automatic success from labels alone.'
    except Exception as exc:
        result['execution_error']=repr(exc)
        raise
    finally:
        for c in result['cases']:
            if c['status']=='pending': c['status']='execution_failure'
        present={c['id'] for c in result['cases']}
        result['cases'].extend(dict(id=p['id'],status='not_completed',predicted=None) for p in inputs if p['id'] not in present)
        result['cost']=dict(input_tokens=sum(c.get('input_tokens',0) for c in result['cases'] if c.get('output_tokens') is not None),
            output_tokens=sum(c.get('output_tokens',0) for c in result['cases']),elapsed_s=sum(c.get('elapsed_s',0) for c in result['cases']))
        write(OUT/'result.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['freeze','run'])
    args=parser.parse_args();freeze() if args.mode=='freeze' else run()
