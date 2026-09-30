"""Read/search the reviewed local corpus. No ontology generation or DB mutation."""
import csv
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'configs/knowledge/lh_input_bundle_20260930/input_manifest.json'


def catalog(scope='current_discovery', step=0):
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    runs = {r['id']: r for r in manifest['runs']}
    if scope not in runs:
        raise ValueError('등록된 탐색 범위를 선택하세요.')
    run = runs[scope]
    if scope == 'historical_change':
        if not 0 <= step <= len(run['updates']):
            raise ValueError('역사 자료 단계가 범위를 벗어납니다.')
        ids = run['initial_source_ids'] + sum(run['updates'][:step], [])
    else:
        if step != 0:
            raise ValueError('단계 선택은 역사 자료에만 적용합니다.')
        ids = run.get('source_ids', run.get('new_source_ids', []))
        if run.get('base_run'):
            ids = runs[run['base_run']]['source_ids'] + ids
    files = []
    for source in manifest['selected_sources']:
        if source['source_id'] not in ids:
            continue
        for index, item in enumerate(source['input_files']):
            files.append(dict(file_id=f"{source['source_id']}:{index}",
                              source_id=source['source_id'], title=source['title'],
                              source_url=source['source_url'], rights=source['rights'],
                              version=source.get('version_header'),
                              encoding=source.get('csv_encoding') or 'utf-8-sig',
                              **item))
    return dict(bundle_id=manifest['bundle_id'], manifest_sha256=sha256(MANIFEST.read_bytes()).hexdigest(),
                scope=scope, step=step, items=files)


def _path(item):
    path = (ROOT / item['path']).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise ValueError('프로젝트 밖 자료는 탐색할 수 없습니다.')
    if not path.is_file() or sha256(path.read_bytes()).hexdigest() != item['sha256']:
        raise ValueError(f"확정 입력 누락 또는 해시 불일치: {item['file_id']}")
    return path


def _blocks(item):
    path = _path(item)
    if path.suffix == '.csv':
        with path.open(encoding=item['encoding'], newline='') as stream:
            reader = csv.DictReader(stream)
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError('CSV 열 수 불일치')
                yield dict(text='\n'.join(f'{k}: {v}' for k, v in row.items()),
                           locator=dict(format='csv', physical_row=reader.line_num))
    elif path.suffix == '.pdf':
        from .parsers import plan_units, parse_unit
        for unit in plan_units(path, 'pdf'):
            yield from parse_unit(path, 'pdf', unit)
    elif path.suffix in {'.txt', '.md'}:
        text = path.read_text(encoding='utf-8-sig')
        section, headers, offset = '', [], 0
        for line_number, line in enumerate(text.splitlines(keepends=True), 1):
            if line.startswith('#'):
                section, headers = line.strip(), []
            if line.startswith('|') and not headers:
                headers = [line.strip()]
            # ponytail: literal lines/spans preserve excerpts; no semantic chunking dependency.
            for start in range(0, len(line), 2000):
                part = line[start:start + 2000]
                if part.strip():
                    yield dict(text=part, locator=dict(format=path.suffix[1:], line=line_number,
                               start_char=offset + start, end_char=offset + start + len(part),
                               section=section, table_headers=headers if line.startswith('|') else []))
            offset += len(line)
    else:
        raise ValueError('지원하지 않는 확정 입력 형식')


def read(file_id, scope='current_discovery', step=0, offset=0, limit=20):
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError('offset은 0 이상, limit은 1~100이어야 합니다.')
    data = catalog(scope, step)
    item = next((f for f in data['items'] if f['file_id'] == file_id), None)
    if item is None:
        raise KeyError(file_id)
    blocks, more = [], False
    for index, block in enumerate(_blocks(item)):
        if index < offset:
            continue
        if len(blocks) == limit:
            more = True
            break
        blocks.append(dict(block_index=index, **block))
    return dict(bundle_id=data['bundle_id'], manifest_sha256=data['manifest_sha256'],
                source=item, items=blocks, next_offset=offset + len(blocks) if more else None)


def search(query, scope='current_discovery', step=0, limit=20):
    terms = set(re.findall(r'\w+', query.casefold()))
    if not terms or not 1 <= limit <= 50:
        raise ValueError('검색어와 1~50의 limit이 필요합니다.')
    data = catalog(scope, step)
    matches = []
    for item in data['items']:
        for index, block in enumerate(_blocks(item)):
            score = sum(term in block['text'].casefold() for term in terms)
            if score:
                matches.append(dict(file_id=item['file_id'], title=item['title'],
                                    block_index=index, score=score, **block))
                # ponytail: bounded lexical search over a small local corpus; index when this grows.
                matches.sort(key=lambda m: -m['score'])
                del matches[limit:]
    return dict(bundle_id=data['bundle_id'], manifest_sha256=data['manifest_sha256'],
                scope=scope, step=step, query=query, items=matches)
