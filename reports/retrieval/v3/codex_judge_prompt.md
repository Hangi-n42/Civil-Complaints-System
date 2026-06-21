# Codex 작업 지시: 민원 검색 평가셋(qrels) LLM 채점 — 본인 OpenAI 토큰 사용

너는 이 프로젝트(한국어 민원 RAG 검색, BE2)의 **검색 평가셋 qrels를 채점**한다.
`data/evaluation/v3_rebuild/judge_input.jsonl`의 각 (쿼리, 후보)쌍을 아래 루브릭으로 0/1/2
채점하는 **파이썬 스크립트를 작성하고, 너의 OpenAI API 토큰으로 직접 실행**하라.

## 입력
- `data/evaluation/v3_rebuild/judge_input.jsonl` (민원만, 약 9천 줄)
  각 줄(JSON): `{query_id, query, case_id, doc_text, high_impact}`
  - `query` = 기준 민원 원문, `doc_text` = 후보 과거 사례 본문(최대 2000자)
  - `high_impact=true` = 상위권 후보(검증 우선)

## 채점 루브릭 (judge의 system 프롬프트로 그대로 사용)
```
당신은 민원 검색 관련성 평가 전문가입니다. 핵심 질문은 "두 민원이 닮았는가"가 아니라
"이 과거 사례(Chunk)를 기준 민원(Query)의 답변에 넣어도 안전하게 재사용할 수 있는가"입니다.
닮았더라도 결론이 반대거나 요건·제도·시점이 다르면 위험합니다.

[1단계 — 핵심 3축을 각각 0/1/2로 채점]
1) issue: 민원인이 실제로 해결받으려는 1차 요구가 같은가('답변이 달라지는 구체 수준').
   실체·절차를 함께 물으면 실체 쟁점을 issue로. 2=동일 / 1=유사·일부 다름 / 0=다름
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
 "score":<0|1|2>,"reason":"<결론 안전성 중심 1~2문장>"}
```

## 채점 방법
- **너의 구독 모델로 직접 채점한다 — 외부 OpenAI API 키를 쓰지 마라**(네 세션/구독 토큰만 사용).
- 각 pair: 위 루브릭을 기준으로 `query`와 `doc_text`를 보고 JSON 1개를 산출.
- 같은 입력은 같은 결과가 나오도록 일관되게(결정적으로) 채점.
- 8,732건은 배치로 처리하되(효율적 방식은 네가 선택), **진행 중 자주 파일에 append 저장**(중단 대비).
- 파일 입출력 `encoding='utf-8'`, JSON 파싱은 강건하게(코드블록/trailing comma/control char 보정).

## 출력
- `data/evaluation/v3_rebuild/qrels_raw_codex.jsonl` (append, 한 줄 1 pair)
  `{query_id, case_id, score, axes, risk_flags, reason, high_impact, judge:"codex", model:"<사용모델>"}`
- **resume**: 재실행 시 이미 `score`가 null이 아닌 `(query_id|case_id)`는 스킵(None=에러는 재채점)

## 완료 후 보고
- 총 채점 수 / score 분포(0·1·2 개수) / 에러(None) 수 / 소요 시간 / 사용 모델·총 토큰

## 주의
- "닮음"이 아니라 **"답변에 재사용해도 안전한가"**로 채점(루브릭 cap 규칙 필수 준수).
- 이건 절대 gold가 아니라 **LLM-silver**다. temperature=0으로 일관성 유지.
- 결과는 변경 금지 코퍼스(snapshot sha256 fdda4ce9, 민원 9,132) 기준이다.
