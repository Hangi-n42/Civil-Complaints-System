"""Register the frozen local K1 originals via K2 API; no network source downloads."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--api-base-url', default='http://127.0.0.1:8001')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'configs/knowledge/pilot_v1/sources.json').read_text(encoding='utf-8'))
    registrations = []
    with httpx.Client(base_url=args.api_base_url.rstrip('/') + '/api/v1/knowledge', timeout=60) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()['data']

        for source in manifest['sources']:
            path = ROOT / source['raw_path']
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != source['sha256']:
                raise ValueError(f"고정 원문 hash 불일치: {source['source_id']}")
            scope = source['corpus_scope']
            if isinstance(scope, str):
                if scope != '#cntntsView 본문':
                    raise ValueError('지원하지 않는 비구조화 범위')
                scope = {'selector': '#cntntsView'}
            metadata = dict(title=source.get('title', source['source_id']), publisher=source.get('publisher', '한국토지주택공사'),
                            namespace='lh-pilot-v1', external_id=source['source_id'], source_url=source['source_url'],
                            rights={'status': 'allowed' if source['source_id'] == 'complex_registry_csv' else 'unknown',
                                    'note': json.dumps(source['rights'], ensure_ascii=False)},
                            dates=[{'role': source.get('document_date_basis', source.get('document_date_kind', '문서 기준일')),
                                    'value': source['document_date'],
                                    'precision': 'month' if len(source['document_date']) == 7 else 'day'}] if source.get('document_date') else [],
                            acquired_at=source.get('retrieved_at', source.get('original_acquired_at')),
                            selected_scope=scope)
            data = request('POST', '/sources', files={'file': (path.name, content)},
                           data={'metadata': json.dumps(metadata, ensure_ascii=False)})
            registrations.append({'manifest_id': source['source_id'], **data})
            print(source['source_id'], data['disposition'], flush=True)
        versions = [r['source_version_id'] for r in registrations]
        run_id = request('POST', '/runs', json={'kind': 'parse', 'source_version_ids': versions})['run_id']
        while True:
            run = request('GET', f'/runs/{run_id}')
            if run['status'] not in {'queued', 'running', 'cancel_requested'}:
                break
            time.sleep(0.5)
        report = {'registrations': registrations, 'run': run}
        destination = ROOT / 'data/knowledge/pilot_v1/k2_import_result.json'
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'run_id': run_id, 'status': run['status'], 'counts': run['counts'], 'report': str(destination)}, ensure_ascii=False))
        if run['status'] != 'succeeded':
            raise SystemExit(1)


if __name__ == '__main__':
    main()
