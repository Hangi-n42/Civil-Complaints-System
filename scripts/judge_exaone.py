"""STEP3: exaone 전수 weak-full silver judge (루브릭 v3.1). Ollama(원격 Windows GPU).
resume 지원(이미 채점한 pair 스킵). 사용법: python judge_exaone.py [limit]"""
import json, os, sys, re, requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OLLAMA = os.getenv('OLLAMA_HOST', 'http://100.71.35.78:11434')
MODEL = os.getenv('JUDGE_MODEL', 'exaone3.5:7.8b')

SYSTEM = """당신은 민원 검색 관련성 평가 전문가입니다. 핵심 질문은 "두 민원이 닮았는가"가 아니라
"이 과거 사례(Chunk)를 기준 민원(Query)의 답변에 넣어도 안전하게 재사용할 수 있는가"입니다.
닮았더라도 결론이 반대거나 요건·제도·시점이 다르면 위험합니다.

[1단계 — 핵심 3축을 각각 0/1/2로 채점]
1) issue: 민원인이 실제로 해결받으려는 1차 요구가 같은가('답변이 달라지는 구체 수준'). 실체·절차를
   함께 물으면 실체 쟁점을 issue로. 2=동일 / 1=유사·일부 다름 / 0=다름
2) material_conditions: 대상자·연령·소득·사업장 규모·기간·신청 상태·관할 등 결론을 바꾸는 조건.
   2=대상·규모·기간·시점·관할이 '명백히 동일'할 때만 / 1=하나라도 다름 / 0=반대.
   대상·규모·시점이 조금이라도 다르면 2가 아니라 1(보수적).
3) procedure_remedy: 신청 절차·기한·제출처·불복/구제 수단이 같은가. 2=동일 / 1=부분 / 0=무관

[위험 플래그 — 관측 가능할 때만 true]
- opposite_outcome: 쟁점은 같으나 적용 방향·결론이 반대.
- generic_boilerplate_only: 인사·"검토 후 답변"·부서 연결 등 정형 문구뿐, 실질 정보 없음.
- wrong_legal_framework: 근거 제도·관할 체계가 명백히 다름(본문 관측 시만).
- outdated_or_wrong_jurisdiction: 본문/메타에 기준연도·시행일·관할 불일치가 관측되고 결론·절차를 바꿈.

[2단계 — 후보 점수 → 위험 플래그로 상한(cap)]
(a) issue=2 & material=2 & procedure>=1 → 후보 2 / issue>=1 또는 procedure=2 이고 직접 넣어도 오답
    안 만드는 '구체 정보' 명시 → 후보 1 / 그 외 0.
(b) generic_boilerplate_only→0 / opposite_outcome→원칙0(독립 재사용 절차정보+Query가 그걸 물으면 1)
    / wrong_legal_framework→min(후보,1) / outdated_or_wrong_jurisdiction→min(후보,1)
경계가 모호하면 낮은 점수.

[점수] 2=거의 그대로 인용 가능 / 1=일부 참고 가능 / 0=무용·오답 유발

출력(JSON만):
{"axes":{"issue":<0|1|2>,"material_conditions":<0|1|2>,"procedure_remedy":<0|1|2>},
 "risk_flags":{"opposite_outcome":<bool>,"generic_boilerplate_only":<bool>,
 "wrong_legal_framework":<bool>,"outdated_or_wrong_jurisdiction":<bool>},
 "score":<0|1|2>,"reason":"<결론 안전성 중심 1~2문장>"}"""


def judge(query, doc):
    body = {'model': MODEL, 'stream': False, 'options': {'temperature': 0},
            'messages': [{'role': 'system', 'content': SYSTEM},
                         {'role': 'user', 'content': f'[Query 민원]\n{query}\n\n[Chunk 후보 사례]\n{doc}\n\nJSON만 출력:'}]}
    r = requests.post(f'{OLLAMA}/api/chat', json=body, timeout=120)
    txt = r.json()['message']['content']
    m = re.search(r'\{.*\}', txt, re.DOTALL)
    if not m:
        return None
    js = m.group(0)
    try:
        return json.loads(js)
    except json.JSONDecodeError:
        js2 = re.sub(r',\s*([}\]])', r'\1', js)   # trailing comma 제거
        js2 = re.sub(r'[\x00-\x1f]+', ' ', js2)   # control char 제거
        return json.loads(js2)


def main():
    inp = [json.loads(l) for l in open(os.path.join(ROOT, 'data/evaluation/v3_rebuild/judge_input.jsonl'), encoding='utf-8')]
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else len(inp)
    out_path = os.path.join(ROOT, 'data/evaluation/v3_rebuild/qrels_raw_exaone.jsonl')
    done = set()
    if os.path.exists(out_path):
        for l in open(out_path, encoding='utf-8'):
            try:
                d = json.loads(l)
                if d.get('score') is not None:  # None(에러)은 done에서 제외 → 재채점 대상
                    done.add(d['query_id'] + '|' + d['case_id'])
            except Exception:
                pass
    f = open(out_path, 'a', encoding='utf-8')
    n = 0
    for r in inp[:limit]:
        key = r['query_id'] + '|' + r['case_id']
        if key in done:
            continue
        try:
            res = judge(r['query'], r['doc_text'])
            rec = {'query_id': r['query_id'], 'case_id': r['case_id'], 'score': res.get('score'),
                   'axes': res.get('axes'), 'risk_flags': res.get('risk_flags'),
                   'reason': res.get('reason', ''), 'high_impact': r.get('high_impact'), 'judge': 'exaone'}
        except Exception as e:
            rec = {'query_id': r['query_id'], 'case_id': r['case_id'], 'score': None,
                   'error': str(e)[:80], 'judge': 'exaone'}
        f.write(json.dumps(rec, ensure_ascii=False) + '\n'); f.flush()
        n += 1
        if n % 100 == 0:
            print(f'{n} 채점...')
    print(f'완료 {n} (전체 {len(inp)})')


if __name__ == '__main__':
    main()
