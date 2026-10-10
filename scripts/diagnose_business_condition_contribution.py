"""Reuse the frozen diagnostic runner for the generated partner and conditional reverse."""
import argparse
from copy import deepcopy
from pathlib import Path
import time

import diagnose_business_condition_pair as runner

initial, trial, read, write, sha = runner.initial, runner.trial, runner.read, runner.write, runner.sha
OUT = initial.OUT / 'contribution'


def prepare():
    initial.check()
    assert not (OUT / 'inputs.json').exists()
    auth = read(OUT / 'authorization.json')
    assert auth['maximum_calls'] == 2 and auth['initial_regression_gate_remains_failed'] is True
    cases = next(r for r in read(initial.OUT / 'followup/requests.json') if r['id'] == 'c46_joint')['cases']
    generated = next(r for r in read(initial.OUT / 'generate/result.json')['records'] if r['id'] == 'c46')
    assert cases['Y']['raw'] == generated['construction']['raw']
    canonical = next(r for r in read(initial.OUT / 'stored_inputs.json') if r['id'] == 'c46')['canonical_views']
    inputs = [dict(id='c46_partner_single', phase='single', cases=dict(X=cases['Y']), canonical_views=canonical,
                   prompt=trial.prompt(dict(X=cases['Y']))),
              dict(id='c46_reverse_joint', phase='reverse', cases=dict(X=cases['Y'], Y=cases['X']), canonical_views=canonical,
                   prompt=trial.prompt(dict(X=cases['Y'], Y=cases['X'])))]
    write(OUT / 'inputs.json', inputs)
    dependencies = [OUT / 'authorization.json', OUT / 'criteria.json', OUT / 'inputs.json', Path(__file__),
                    initial.OUT / 'freeze.json', initial.OUT / 'followup/freeze.json',
                    initial.OUT / 'followup/run/result.json', initial.OUT / 'generate/result.json']
    for row in inputs:
        folder = OUT / row['phase']
        folder.mkdir()
        write(folder / 'inputs.json', [row])
        write(folder / 'prepared.json', dict(at=time.time(), files={str(p): sha(p) for p in dependencies + [folder / 'inputs.json']},
                                           runner_sha256=sha(Path(runner.__file__)), calls=1))
    print('Frozen generated partner single1 and conditional reverse1; original9 unchanged')


def preflight():
    for phase in ['single', 'reverse']:
        runner.OUT = OUT / phase
        (runner.OUT / 'runtime_identity.json').write_bytes((OUT / 'runtime_identity.json').read_bytes())
        runner.preflight()


def run(phase):
    if phase == 'reverse':
        review = read(OUT / 'single_review.json')
        assert review['reverse_allowed'] is True and review['single_semantic_correct'] is False
    auth = read(OUT / 'authorization.json')
    assert auth['compute_allocated'] is True and auth['maximum_calls'] == 2
    runner.OUT = OUT / phase
    assert len(read(runner.OUT / 'requests.json')) == 1
    runner.run()


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('mode', choices=['prepare', 'preflight', 'single', 'reverse'])
    mode = cli.parse_args().mode
    run(mode) if mode in {'single', 'reverse'} else globals()[mode]()
