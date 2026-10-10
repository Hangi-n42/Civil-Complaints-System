"""Separately approved compound c47 and normal no-op c13 diagnostics."""
import argparse
from copy import deepcopy
from pathlib import Path
import time

import run_business_source_limit_contrast as generated
import diagnose_business_condition_pair as runner

OUT = generated.OUT / 'diagnostic'
read, write, sha, trial = generated.read, generated.write, generated.sha, generated.prior.trial


def prepare():
    generated.check()
    assert not (OUT / 'inputs.json').exists()
    auth=read(OUT/'authorization.json')
    assert auth['maximum_calls']==3 and auth['construction_gate_remains_failed'] is True
    originals={r['id']:r for r in read(generated.OUT/'inputs.json')}
    constructions={r['id']:r for r in read(generated.OUT/'generate/result.json')['records']}
    rows=[]
    for ident, phase in [('c47','single'),('c47','joint'),('c13','joint')]:
        original=originals[ident]
        cases=dict(X=original['case'])
        if phase=='joint':
            made=constructions[ident]['construction']
            assert generated.trial.construct(original['case'],constructions[ident]['answer'],original['canonical_views'])==made
            cases['Y']=dict(deepcopy(original['case']),raw=made['raw'])
        rows.append(dict(id=ident+'_'+phase,group=ident,cases=cases,canonical_views=original['canonical_views'],prompt=trial.prompt(cases)))
    write(OUT/'inputs.json',rows)
    files=[OUT/'inputs.json',OUT/'authorization.json',OUT/'criteria.json',Path(__file__),generated.OUT/'prepared.json',generated.OUT/'freeze.json',generated.OUT/'generate/result.json',generated.OUT/'construction_review_preliminary.json',generated.OUT/'c47_modality_review.json']
    for ident in ['c47','c13']:
        folder=OUT/ident
        folder.mkdir()
        selected=[r for r in rows if r['group']==ident]
        write(folder/'inputs.json',selected)
        write(folder/'prepared.json',dict(at=time.time(),files={str(p):sha(p) for p in files+[folder/'inputs.json']},runner_sha256=sha(Path(runner.__file__)),calls=len(selected)))


def preflight():
    for ident in ['c47','c13']:
        runner.OUT=OUT/ident
        (runner.OUT/'runtime_identity.json').write_bytes((OUT/'runtime_identity.json').read_bytes())
        runner.preflight()


def run():
    auth=read(OUT/'authorization.json')
    assert auth['compute_allocated'] is True and auth['maximum_calls']==3 and auth['construction_gate_remains_failed'] is True
    for ident in ['c47','c13']:
        runner.OUT=OUT/ident
        runner.run()


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode',choices=['prepare','preflight','run'])
    globals()[cli.parse_args().mode]()
