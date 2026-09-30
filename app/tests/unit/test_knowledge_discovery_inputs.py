import hashlib
import json

import pytest

from app.knowledge import discovery_inputs as inputs


def test_scope_search_read_and_fixed_bytes(tmp_path, monkeypatch):
    sources = []
    for name, group, text in [('current', 'current_discovery', '현재 국민임대'),
                              ('old', 'historical_change', '과거 국민임대'),
                              ('new', 'historical_change', '신규 통합공공임대')]:
        path = tmp_path / (name + '.txt')
        path.write_text(text, encoding='utf-8')
        sources.append(dict(source_id=name, title=name, source_url='https://example.org', rights={},
                            input_files=[dict(path=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())]))
    manifest = tmp_path / 'manifest.json'
    manifest.write_text(json.dumps(dict(bundle_id='test', selected_sources=sources,
        held_sources=[dict(source_id='held')], runs=[dict(id='current_discovery', source_ids=['current']),
        dict(id='historical_change', initial_source_ids=['old'], updates=[['new']])])), encoding='utf-8')
    monkeypatch.setattr(inputs, 'ROOT', tmp_path)
    monkeypatch.setattr(inputs, 'MANIFEST', manifest)
    assert [x['file_id'] for x in inputs.catalog('historical_change')['items']] == ['old:0']
    assert inputs.search('통합공공임대', 'historical_change')['items'] == []
    hit = inputs.search('통합공공임대', 'historical_change', 1)['items'][0]
    assert hit['file_id'] == 'new:0'
    block = inputs.read(hit['file_id'], 'historical_change', 1, hit['block_index'], 1)['items'][0]
    assert block['text'] == '신규 통합공공임대'
    with pytest.raises(KeyError):
        inputs.read('current:0', 'historical_change', 1)
    with pytest.raises(ValueError):
        inputs.catalog('historical_change', 2)
    (tmp_path / 'new.txt').write_text('변조', encoding='utf-8')
    with pytest.raises(ValueError, match='해시 불일치'):
        inputs.read('new:0', 'historical_change', 1)
