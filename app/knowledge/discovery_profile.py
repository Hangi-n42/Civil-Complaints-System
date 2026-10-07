"""Deterministic survey, coverage sampling and run-local lexical ranking of A1 blocks."""
from collections import Counter, defaultdict
from hashlib import sha256
import json
import re


def digest(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def stable_id(block):
    return (block['source_version_id'], json.dumps(block['locator'], sort_keys=True), block['id'])


def csv_values(block):
    """Decode the existing header-labelled CSV block; ambiguous cells stay unresolved."""
    columns = block['locator']['column_names']
    rest, values = block['text'], {}
    for index, column in enumerate(columns):
        prefix = column + ': '
        if not rest.startswith(prefix):
            raise ValueError('CSV 열 문맥 복원 불가')
        rest = rest[len(prefix):]
        if index + 1 < len(columns):
            marker = '\n' + columns[index + 1] + ': '
            if rest.count(marker) != 1:
                raise ValueError('CSV 다중 행 값/열 경계 모호함')
            value, rest = rest.split(marker, 1)
            rest = columns[index + 1] + ': ' + rest
        else:
            value = rest
        values[column] = value.strip()
    return values


def shape(value):
    if not value:
        return 'missing'
    if re.fullmatch(r'\d{4}[-./]\d{1,2}([-./]\d{1,2})?', value):
        return 'date_expression'
    if re.fullmatch(r'[+-]?\d+(\.\d+)?', value):
        return 'number_expression'
    return 'text'


def csv_profile(blocks):
    rows, unresolved = {}, []
    for block in blocks:
        try:
            rows[block['id']] = csv_values(block)
        except ValueError:
            unresolved.append(block['id'])
    columns = blocks[0]['locator']['column_names'] if blocks else []
    counts = {c: Counter(row[c] for row in rows.values()) for c in columns}
    categorical = {c: len(v) <= 32 or bool(re.search(r'유형|종류|분류|구분|상태', c)) for c,v in counts.items()}
    fields = {c: dict(category_basis='열 이름의 분류 신호' if len(v)>32 and categorical[c] else '관측 고유값 32 이하' if categorical[c] else '고카디널리티: 값별 대표는 미선정, 형식만 조사', observed_distinct=len(v), missing=v.get('', 0),
                      observed_categories=dict(sorted(v.items())) if categorical[c] else None,
                      formats=dict(Counter(shape(row[c]) for row in rows.values())),
                      meaning='자료에 관측된 표기; 허용 enum/필수값 판정 아님') for c, v in counts.items()}
    features = {}
    for identifier, row in rows.items():
        covered = set()
        for col, value in row.items():
            covered.add(f'field:{col}:format:{shape(value)}')
            if re.search(r'[,/·+]', value):
                covered.add(f'field:{col}:separator_expression')
            if categorical[col]:
                covered.add(f'category:{col}:{value}')
            if re.search(r'[,/·+]', value) and categorical[col]:
                covered.add(f'mixed:{col}:{value}')
        features[identifier] = covered
    frequency = Counter(f for values in features.values() for f in values)
    unmet = set(frequency)
    by_id = {b['id']: b for b in blocks}
    selected = []
    # ponytail: greedy set cover for the bounded pilot; no cross-product or learned sampler.
    while unmet:
        identifier = min(features, key=lambda i: (-len(features[i] & unmet),
            -sum(1 / frequency[f] for f in sorted(features[i] & unmet)), len(by_id[i]['text']), stable_id(by_id[i])))
        gained = features[identifier] & unmet
        if not gained:
            break
        selected.append(dict(block_id=identifier, covered_features=sorted(gained),
                             reason='미충족 특징 최다 → 희소성 → 입력 길이 → 안정 ID'))
        unmet -= gained
    return dict(row_count=len(blocks), fields=fields, selected=selected,
                unresolved_block_ids=unresolved, feature_count=len(frequency), uncovered_features=sorted(unmet))


def table_key(block):
    loc = block['locator']
    if 'table' not in loc and 'row' not in loc:
        return None
    return (block['source_version_id'], loc.get('member'), loc.get('physical_page'), loc.get('side'),
            loc.get('table'), loc.get('element_path'))


def contexts(blocks):
    """Preserve existing locators and include row/header/neighbour evidence, never infer missing captions."""
    tables = defaultdict(list)
    for block in blocks:
        key = table_key(block)
        if key is not None:
            tables[key].append(block)
    result = {}
    order = {b['id']: i for i,b in enumerate(blocks)}
    for index, block in enumerate(blocks):
        loc = block['locator']; key = table_key(block)
        is_table = key is not None or bool(loc.get('table_headers')) or loc['format'] == 'csv'
        ids = {block['id']}
        notes = []
        if key is not None:
            ids.update(b['id'] for b in tables[key] if b['locator'].get('row') in {0, loc.get('row')})
            notes.append('다단 헤더·제목·단위·각주 전체 복원 여부 미확인')
        elif loc.get('table_headers'):
            # A1 keeps the correct contiguous table's header text (including the 49e40d3 fix).
            for other in reversed(blocks[:index]):
                if not other['locator'].get('table_headers'):
                    break
                if other['text'].strip() in loc['table_headers']:
                    ids.add(other['id'])
        if is_table and loc['format'] != 'csv':
            for other in blocks[max(0, index-1):index+2]:
                if other['source_version_id'] == block['source_version_id']:
                    ids.add(other['id'])
            notes.append('인접 원문 제공; 각주/단위의 의미 연결은 검수 필요')
        result[block['id']] = dict(block_ids=sorted(ids, key=order.get),
            status='unconfirmed' if notes else 'recorded', notes=notes,
            title=loc.get('table_caption') or loc.get('section'), headers=loc.get('table_headers', loc.get('column_names', [])))
    return result


def numbered_items(blocks):
    """A bounded structural signal, not semantic segmentation or a completeness oracle."""
    items = []
    for block in blocks:
        dates = [m.span() for m in re.finditer(r'\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.', block['text'])]
        matches = [m for m in re.finditer(r'(?<!\S)([1-9]\d?)(?:의\d+)?[.)]\s+(?=[^\d\s])', block['text'])
                   if not any(start <= m.start() < end for start, end in dates)]
        # Require the beginning of a numbered sequence; isolated numeric prose is not a list.
        if not {'1', '2'} <= {m[1] for m in matches}: continue
        items.extend(dict(block_id=block['id'], marker=m[0], start=m.start(), end=m.end()) for m in matches)
    return items


def survey(files, blocks):
    profiles, frontier, context_map = [], [], {}
    for file in files:
        selected = [b for b in blocks if b['file_id'] == file['file_id']]
        context_map.update(contexts(selected))
        profile = dict(file_id=file['file_id'], source_version_id=file['source_version_id'], group=file.get('group') or file['file_id'],
            title=file['title'], role=file.get('role'), block_count=len(selected),
            sections=sorted({str(b['locator']['section']) for b in selected if b['locator'].get('section')}),
            table_count=len({table_key(b) for b in selected if table_key(b) is not None}),
            exception_block_ids=[b['id'] for b in selected if re.search('제외|다만|경우|변경|예외', b['text'])],
            reference_expressions=sorted({m for b in selected for m in re.findall(r'제\d+조(?:의\d+)?|별표\s*\d+', b['text'])}))
        profile['table_count'] += sum(bool(b['locator'].get('table_headers')) and (n==0 or not selected[n-1]['locator'].get('table_headers')) for n,b in enumerate(selected))
        if selected and selected[0]['locator']['format'] == 'csv':
            profile['table_count'] = 1
            profile['csv'] = csv_profile(selected)
            selection = {s['block_id']: s for s in profile['csv']['selected']}
            selected = [b for b in selected if b['id'] in selection]
        else:
            selection = {b['id']: dict(reason='선택한 정의·규정·API 원문의 필수 절/표', covered_features=[]) for b in selected}
        profiles.append(profile)
        batch, size = [], 0
        for block in selected:
            cost = len(json.dumps(dict(text=block['text'], locator=block['locator'], context=context_map[block['id']]), ensure_ascii=False))
            limit = 1600 if block['locator']['format']=='csv' else 3200
            if batch and size + cost > limit:
                frontier.append(_batch(file, batch, selection)); batch, size = [], 0
            batch.append(block); size += cost
        if batch:
            frontier.append(_batch(file, batch, selection))
    # Rotate source groups within each priority, then novelty/cost/stable IDs.
    pending, ordered, last = list(frontier), [], None
    while pending:
        priority = min(g['priority'] for g in pending)
        choices = [g for g in pending if g['priority'] == priority]
        group = min(choices, key=lambda g: (g['source_group'] == last, -len(g['features']), g['input_chars'], g['id']))
        pending.remove(group); ordered.append(group); last = group['source_group']
    return profiles, ordered, context_map


def _batch(file, blocks, selection):
    csv = blocks[0]['locator']['format'] == 'csv'
    features = sorted({f for b in blocks for f in selection[b['id']]['covered_features']})
    exception = any('missing' in f or f.startswith('mixed:') for f in features)
    return dict(id='g_' + digest([stable_id(b) for b in blocks])[:20], file_id=file['file_id'],
        block_ids=[b['id'] for b in blocks], source_group=file['manifest_source_id'],
        priority=2 if csv and exception else 3 if csv else 1, features=features,
        required=True, input_chars=sum(len(b['text']) for b in blocks), round=0,
        reason='대표/예외 greedy coverage' if csv else '선택 원문 필수 절/표', status='unvisited')


class FrozenIndex:
    """One in-memory index per execution; only ranking utilities from K6 are reused."""
    def __init__(self, blocks, *, preserve_numbers=False):
        import bm25s
        from app.retrieval.pipeline.stages.bm25_retriever import _tokenize_korean, _to_bm25s_tokens
        self.blocks = blocks
        def tokenize(texts):
            tokens = _tokenize_korean(texts)
            if preserve_numbers:
                for text, row in zip(texts, tokens):
                    row.extend('numeric_' + n.replace('.', '_') for n in
                               re.findall(r'(?<![0-9A-Za-z_.])\d+(?:\.\d+)?(?![0-9A-Za-z_.])', text))
            return tokens
        self.tokenize = tokenize
        self.convert = _to_bm25s_tokens
        self.tokens = self.tokenize([b['text'] for b in blocks])
        self.engine = bm25s.BM25()
        self.ready = bool(blocks and any(self.tokens))
        if self.ready:
            self.engine.index(self.convert(self.tokens), show_progress=False)

    def search(self, query, allowed, limit=6):
        if not self.ready:
            return []
        tokens = self.tokenize([query])
        if not tokens[0]:
            return []
        ids, scores = self.engine.retrieve(self.convert(tokens), k=len(self.blocks), show_progress=False)
        groups, duplicates, seen = defaultdict(list), [], set()
        for index, score in zip(ids[0], scores[0]):
            block = self.blocks[int(index)]
            if float(score) <= 0 or block['id'] not in allowed:
                continue
            text = re.sub(r'\s+', '', block['text'])
            hit = dict(block_id=block['id'], score=float(score), file_id=block['file_id'])
            if text in seen:
                duplicates.append(hit)
            else:
                groups[block['source_group']].append(hit); seen.add(text)
        ranked = []
        while groups:
            for key in list(groups):
                ranked.append(groups[key].pop(0))
                if not groups[key]:
                    del groups[key]
        return (ranked + duplicates)[:limit]
