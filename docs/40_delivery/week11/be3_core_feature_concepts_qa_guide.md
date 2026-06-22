# BE3 핵심 기능 질의응답 가이드

이 문서는 BE3 Generation 파트의 핵심 기능인 PromptFactory, Civil LLM-Rubric, Prometheus 재생성, ARES-lite 평가에 대해 질문을 받았을 때 바로 설명할 수 있도록 정리한 요약 자료입니다.

## 1. 전체 파이프라인 한 줄 요약

BE3 파이프라인은 민원 입력을 받아 검색 근거를 확보하고, PromptFactory로 회신 프롬프트를 만들고, 모델 답변을 생성한 뒤, Civil LLM-Rubric과 ARES-lite로 품질과 근거성을 평가하며, 필요하면 Prometheus 피드백으로 답변을 한 번 더 개선하는 구조입니다.

```text
민원 데이터
→ 검색/Chroma context 확보
→ PromptFactory prompt 생성
→ LLM 답변 생성
→ JSON/문단/인용 후처리
→ Civil LLM-Rubric 품질 평가
→ 필요 시 Prometheus 피드백 기반 재생성
→ ARES-lite로 검색·근거·질의대응 진단
→ 벤치마크 리포트 생성
```

## 2. PromptFactory

PromptFactory는 답변 생성 프롬프트의 단일 진입점입니다. 이전에는 벤치마크 스크립트나 생성 경로마다 프롬프트를 따로 만들 수 있었지만, 현재는 스키마, 근거 context, citation 규칙, 민원 회신 문체를 한곳에서 관리하는 방향입니다.

### 왜 필요한가

- 모델 성능과 프롬프트 결함을 분리하기 위해 필요합니다.
- 답변 스키마가 흔들리거나 citation 규칙이 모드별로 달라지는 문제를 줄입니다.
- direct benchmark, API generation, auto-retrieve 경로가 같은 기준으로 프롬프트를 만들 수 있게 합니다.

### PromptFactory가 넣는 핵심 요소

- 검색된 context block
- JSON required key 지시
- citation 작성 규칙
- 민원 회신 문체와 금지 표현
- 토픽/복잡도별 안내문
- routing_trace, derived_query 같은 디버깅 정보

### 세 가지 모드

| 모드 | 의미 | 주 사용 상황 |
|---|---|---|
| `default` | 기본 생성 모드입니다. 충분한 context와 일반적인 회신 문체를 사용합니다. | 정상적인 답변 생성 |
| `compact` | context 길이와 개수를 줄이고 JSON-only 지시를 더 강하게 줍니다. | 기본 생성 실패 후 retry, 긴 prompt 부담 완화 |
| `force_json` | JSON-only와 required key 누락 방지 지시를 가장 강하게 줍니다. | 스키마 준수가 특히 중요한 수동/평가 경로 |

현재 GenerationService의 일반 retry 흐름은 주로 `default → compact`입니다. `force_json`은 PromptFactory와 벤치마크 경로에서 지원되지만, 일반 생성의 모든 fallback 단계에 항상 자동으로 들어가는 것은 아닙니다.

### citation 규칙

- citations는 반드시 검색 context chunk에서만 선택해야 합니다.
- citation 객체는 내부 평가와 검증을 위해 유지합니다.
- 최근 회신 형식에서는 답변 본문 맨 마지막에 `[[출처 1]]` 같은 출처 토큰을 노출하지 않는 방향으로 정리했습니다.
- strict citation match는 citation의 `chunk_id`, `case_id`, snippet 등이 실제 검색 context와 맞는지 보는 형식적 검증입니다. 이것이 높다고 해서 답변 의미가 항상 맞다는 뜻은 아닙니다.

### 근거 0개 처리

검색 근거가 0개이면 환각 답변을 막기 위해 즉시 실패 또는 fallback으로 처리합니다. 이때 다음 정보를 남겨야 원인을 추적할 수 있습니다.

- `derived_query`
- `collection_name`
- `top_k`
- `filters`
- `routing_trace`
- topic, complexity, route_key, strategy_id

## 3. GenerationService와 direct benchmark

GenerationService는 실제 API 생성 흐름을 담당하고, direct benchmark는 API 서버를 거치지 않고 같은 생성 로직을 평가용으로 실행하는 경로입니다.

### direct benchmark에서 하는 일

1. 입력 dataset을 읽습니다.
2. Chroma DB에서 관련 context를 검색합니다.
3. PromptFactory로 프롬프트를 만듭니다.
4. Ollama/LLM을 호출합니다.
5. 모델 출력 JSON을 파싱합니다.
6. 파싱 실패나 문단 깨짐을 후처리로 보정합니다.
7. citation을 검증하고 필요한 경우 repair합니다.
8. Civil LLM-Rubric 평가를 수행합니다.
9. 낮은 점수면 Prometheus 재생성을 시도합니다.
10. ARES-lite로 검색 근거와 답변 대응성을 진단합니다.
11. `.json`, `.jsonl`, `.md` 리포트를 생성합니다.

### raw_responses와 parsed_answers 차이

| 파일 | 의미 |
|---|---|
| `raw_responses.jsonl` | 모델이 처음 낸 원본 응답입니다. JSON 깨짐, 내부 라벨, 불필요한 문구가 남아 있을 수 있습니다. |
| `parsed_answers.jsonl` | 파싱, 정규화, 후처리를 거쳐 실제 평가와 비교에 쓰는 답변입니다. |

따라서 사용자가 실제로 읽을 답변 품질은 주로 `parsed_answers.jsonl` 또는 readable summary를 기준으로 봅니다.

## 4. Civil LLM-Rubric

Civil LLM-Rubric은 최종 민원 회신 품질을 평가하는 장치입니다. ARES가 검색·근거 진단에 가깝다면, Rubric은 사용자가 받는 답변의 종합 품질을 봅니다.

### 평가 항목

| 항목 | 의미 |
|---|---|
| Q0 | 종합 회신 품질과 사용자 만족도 |
| Q1 | 공공기관 회신 문체, 자연스러움, 정중함 |
| Q2 | 제공된 근거만으로 답변 가능한지 |
| Q3 | 주요 주장에 citation이 붙어 있는지 |
| Q4 | citation이 실제 주장을 잘 뒷받침하는지 |
| Q5 | 가장 직접적이고 적절한 근거를 골랐는지 |
| Q6 | 반복, 내부 라벨, 불필요한 문구가 없는지 |
| Q7 | 간결성과 효율성 |

현재 구현은 Q0~Q7 중심입니다. 초기 논문 설명의 Q8 개념은 참고했지만, 현재 코드의 주요 산출물은 Q0~Q7입니다.

### 1~4점과 0~10점

Rubric은 원래 1~4점 척도 개념을 유지하면서, 보고서에서는 0~10점으로 변환한 점수도 같이 제공합니다.

```text
score_0_10 = (score_1_4 - 1) / 3 * 10
```

예를 들어 1~4점 기준 2.5점은 0~10점 기준 약 5.0점입니다.

### judge_status

| 상태 | 의미 |
|---|---|
| `llm_judge` | LLM judge가 정상 평가했습니다. |
| `rule_fallback` | LLM judge를 쓰지 못했거나 direct/local 조건에서 rule 기반 보조 평가로 대체했습니다. |
| `error` | 평가 자체에 실패했습니다. |

### safety layer

Rubric에는 점수만 보는 것이 아니라 위험 요소를 감점하거나 human review 대상으로 표시하는 안전장치가 있습니다.

대표 위험 요소:

- 답변 없음
- 내부 metadata 노출
- conclusion reversal
- 근거 없는 확약
- citation 누락
- 민원과 다른 사례 답변
- 과도한 사업계획/권한 초과 표현

`safety_layer.cap_applied = true`이면 최종 Q0가 일정 수준 이상 올라가지 못하도록 제한될 수 있습니다.

## 5. Prometheus

Prometheus는 독립적인 최종 평가기가 아니라, 낮은 점수 답변을 개선하기 위한 피드백·재생성 모듈입니다.

### 역할

- Rubric에서 낮게 나온 항목을 읽습니다.
- 어떤 부분을 고쳐야 하는지 feedback을 만듭니다.
- 기존 답변을 개선하는 revision prompt를 구성합니다.
- 모델을 다시 호출해 개선 답변을 생성합니다.
- 개선 답변이 기존보다 나쁘지 않은지 다시 평가합니다.

### 언제 동작하나

보통 다음 조건에서 동작합니다.

- Q0 또는 세부 Q 점수가 낮음
- low_score_items가 존재함
- 답변이 비어 있지 않음
- 재생성 시도 횟수가 남아 있음

현재 기본 정책은 과도한 비용과 지연을 막기 위해 재생성을 보통 1회로 제한하는 방향입니다.

### 왜 항상 좋아지지는 않나

- 검색 context 자체가 약하면 재생성해도 답변 근거가 좋아지기 어렵습니다.
- Q0는 올라가도 ARES faithfulness가 떨어질 수 있습니다.
- 그래서 Prometheus 결과는 반드시 재평가와 acceptance gate를 거쳐야 합니다.

말할 때는 “Prometheus가 답변을 무조건 고친다”가 아니라 “Rubric의 낮은 항목을 기반으로 제한적으로 재생성을 시도하고, 나빠지면 채택하지 않는다”고 설명하는 것이 정확합니다.

## 6. ARES-lite

ARES-lite는 답변의 최종 만족도보다 RAG 파이프라인의 문제 원인을 진단하기 위한 평가입니다.

### 평가 축

| 축 | 의미 |
|---|---|
| context_relevance | 검색된 context가 민원 해결에 관련 있는지 |
| answer_faithfulness | 답변이 context에 근거해 충실하게 작성됐는지 |
| answer_relevance | 답변이 민원 요청 세그먼트를 잘 해결했는지 |

### 통합 judge

현재 방향은 LLM 기반 integrated judge입니다. 즉 context relevance, faithfulness, answer relevance를 각각 따로 호출하지 않고 한 번의 LLM 판단으로 함께 평가합니다.

장점:

- 세 축 사이의 관계를 같이 볼 수 있습니다.
- LLM 호출 수가 줄어듭니다.
- rule 기반 평가보다 의미적 판단이 낫습니다.

주의점:

- 최근 실험에서 ARES integrated judge는 꽤 보수적으로 high risk를 많이 주는 경향이 있었습니다.
- 따라서 점수 자체보다 어떤 축이 낮은지, unsupported_claims와 missing_segments가 무엇인지 보는 것이 중요합니다.
- rule 기반 ARES는 기본 평가로 쓰기보다 smoke test, fallback, 비교 실험용으로 남기는 것이 적절합니다.

### overall score

ARES-lite의 overall score는 보통 다음 가중치로 계산합니다.

```text
overall = context_relevance * 0.30
        + answer_faithfulness * 0.40
        + answer_relevance * 0.30
```

faithfulness 비중이 가장 큰 이유는 민원 답변에서 근거 없는 확정 표현이 가장 위험하기 때문입니다.

## 7. Rubric과 ARES를 같이 보는 법

Rubric과 ARES는 같은 평가가 아닙니다. 둘을 같이 봐야 원인이 보입니다.

| 패턴 | 해석 |
|---|---|
| Rubric Q0 낮음 + ARES faithfulness 낮음 | 근거 없는 답변 가능성이 큽니다. |
| Rubric Q0 낮음 + ARES context 낮음 | 생성보다 검색 실패 가능성이 큽니다. |
| Rubric Q7 낮음 + ARES relevance 정상 | 답은 맞지만 장황하거나 비효율적일 수 있습니다. |
| Rubric Q3/Q4 낮음 + ARES faithfulness 낮음 | citation과 주장 연결이 약합니다. |
| Rubric Q1 낮음 + ARES 정상 | 내용은 맞지만 공공기관 회신 문체가 부족합니다. |
| Rubric 정상 + ARES high risk | 보기에는 자연스럽지만 근거성이 약할 수 있어 수동 검토가 필요합니다. |

## 8. 최근 벤치마크에서 봐야 할 핵심 지표

벤치마크 결과를 설명할 때는 단순 평균만 말하지 말고 아래 지표를 함께 봐야 합니다.

### 생성 품질 지표

- 성공 case 수
- fallback/failed case 수
- 평균 답변 길이
- 문단 형식 일관성
- 내부 라벨 노출 여부
- `감사합니다.` 종결문 중복 여부

### 파싱·후처리 지표

- `parse_success_rate`
- `postprocess_success_rate`
- raw JSON이 깨졌는지
- 후처리로 얼마나 복구됐는지

### citation 지표

- citation count
- citation match rate
- strict citation match
- repaired citation match

### Rubric 지표

- final Q0 평균
- Q별 평균
- safety cap 적용률
- human_review_required 비율
- Prometheus revision count
- judge_status 분포

### ARES 지표

- overall 평균
- context relevance 평균
- answer faithfulness 평균
- answer relevance 평균
- risk_level 분포
- unsupported_claims 발생률
- missing_segments 발생률

## 9. 평가 점수를 얼마나 믿을 수 있는가

질문을 받았을 때 가장 중요한 답변은 “이 점수는 사람 평가를 완전히 대체하는 절대값이 아니라, 재현 가능한 기준과 근거 로그를 가진 자동 평가 신호”라는 것입니다. 신뢰도는 단일 점수가 아니라 여러 장치가 서로 보완하는 방식으로 확보합니다.

### 객관성을 확보하는 근거

| 근거 | 설명 |
|---|---|
| 평가 기준 문서화 | Civil LLM-Rubric의 Q0~Q7 기준과 ARES의 3개 축을 문서로 고정해, 매번 같은 기준으로 평가합니다. |
| 입력·출력 재현성 | dataset, config, model, prompt mode, output directory를 고정해 같은 조건에서 다시 실행할 수 있습니다. |
| 다중 평가축 | Rubric은 최종 회신 품질을 보고, ARES는 context relevance, faithfulness, answer relevance로 원인을 진단합니다. |
| 근거 기반 검증 | citation, retrieved context, unsupported_claims, missing_segments를 함께 남겨 점수 이유를 추적할 수 있습니다. |
| safety layer | 결론 반전, 근거 없는 확약, 내부 라벨 노출처럼 위험한 답변은 평균 점수가 높아도 cap이나 review 대상으로 잡습니다. |
| 사람 검토 샘플 | 고위험·중위험·정상 샘플을 따로 뽑아 자동 평가가 납득되는지 수동 검토합니다. |
| 평가 산출물 보존 | raw response, parsed answer, rubric score, ARES score, transition report를 남겨 사후 검증이 가능합니다. |

### 그래서 “객관적인가?”라고 물으면 이렇게 답하면 됩니다

완전한 의미의 객관 평가는 아닙니다. LLM 기반 평가는 사람 평가처럼 해석 여지가 있기 때문입니다. 대신 현재 구현은 평가 기준을 고정하고, 같은 입력에 같은 절차를 적용하며, Rubric과 ARES를 분리해 답변 품질과 근거성을 따로 봅니다. 또한 점수뿐 아니라 citation, context, unsupported claim, missing segment, safety cap, human review flag를 함께 남기기 때문에 왜 낮거나 높은 점수가 나왔는지 추적할 수 있습니다. 따라서 “절대적인 정답 점수”라기보다 “재현 가능하고 감사 가능한 자동 평가 지표”라고 설명하는 것이 가장 정확합니다.

### 점수 해석 시 주의할 점

- Q0 평균 하나만 보고 모델이 좋다고 말하면 안 됩니다.
- ARES 점수가 낮다고 항상 생성 모델만 문제인 것은 아닙니다. 검색 context가 약한 경우도 많습니다.
- Rubric 점수가 높아도 ARES faithfulness가 낮으면 근거 없는 자연스러운 답변일 수 있습니다.
- ARES integrated judge는 보수적으로 위험을 크게 잡을 수 있어 사람 검토 샘플로 보정 판단이 필요합니다.
- rule fallback 점수와 LLM judge 점수는 신뢰 수준이 다르므로 `judge_status`를 함께 봐야 합니다.

### 발표용 한 문장

“현재 평가 점수는 사람 평가를 대체하는 절대 점수가 아니라, 고정된 루브릭과 근거성 진단, safety cap, 사람 검토 샘플을 결합한 재현 가능한 품질 신호입니다.”

## 10. 자주 받을 질문과 답변

### Q. PromptFactory가 정확히 뭘 하나요?

검색 context, JSON 스키마, citation 규칙, 민원 회신 문체를 한 번에 조립하는 프롬프트 생성기입니다. 벤치마크와 API 생성이 같은 기준으로 답변을 만들게 하는 핵심 진입점입니다.

### Q. `default`, `compact`, `force_json`은 어떻게 다르나요?

`default`는 일반 생성, `compact`는 짧은 context와 강한 JSON-only 지시를 쓰는 재시도용, `force_json`은 스키마 준수를 최우선으로 하는 강제 JSON 모드입니다.

### Q. strict citation match가 높으면 답변이 좋은 건가요?

형식적으로 citation이 검색 context와 잘 연결됐다는 뜻입니다. 하지만 citation이 의미적으로 최적인지, 답변 결론이 맞는지는 Rubric Q4/Q5와 ARES faithfulness를 같이 봐야 합니다.

### Q. Civil LLM-Rubric은 무엇을 평가하나요?

사용자가 받는 최종 민원 회신의 품질을 봅니다. 문체, 근거, citation, 중복, 간결성, 종합 만족도를 Q0~Q7로 평가합니다.

### Q. ARES와 Rubric의 차이는 뭔가요?

Rubric은 최종 답변 품질 점수이고, ARES는 검색 context와 답변 사이의 근거성, 관련성, 누락 요청을 진단합니다. Rubric은 “답변이 좋은가”, ARES는 “왜 문제가 생겼는가”에 가깝습니다.

### Q. Prometheus는 평가 모델인가요?

아닙니다. 낮은 Rubric 항목을 보고 답변을 개선하도록 피드백과 재생성 prompt를 만드는 모듈입니다.

### Q. 답변 생성 후 재생성까지 하면 LLM을 몇 번 호출하나요?

경로에 따라 다릅니다. 질문을 받으면 먼저 “direct 벤치마크 기준인지, LLM judge를 모두 켠 full 평가 기준인지”를 구분해서 답해야 합니다.

| 기준 | 호출 수 | 설명 |
|---|---:|---|
| 현재 direct 벤치마크 기본 흐름 | 보통 1회, 재생성 시 최대 2회 | 첫 답변 생성 1회가 기본입니다. 낮은 점수로 Prometheus revision이 필요하면 개선 답변 생성 1회가 추가됩니다. 이 경로의 Civil LLM-Rubric은 `llm_call=None`으로 실행되어 Q0~Q7별 LLM judge 호출을 하지 않고 rule/runtime 평가를 사용합니다. |
| direct 벤치마크 + ARES integrated judge | 보통 2회, 재생성 시 최대 3회 | 위 direct 호출 수에 ARES integrated judge 1회가 추가됩니다. ARES는 context relevance, faithfulness, answer relevance를 한 번에 평가합니다. |
| LLM Rubric full judge + Prometheus feedback + 재평가 | 최대 19회 | 첫 생성 1회 + 초기 Rubric Q0~Q7 8회 + Prometheus feedback 1회 + 필요 시 재생성 1회 + 최종 Rubric Q0~Q7 8회 = 최대 19회입니다. |

따라서 네가 적은 `첫 생성 1 + 초기 루브릭 8 + 피드백 1 + 재생성 1 + 최종 루브릭 8 = 최대 19회`는 “Q별 LLM judge와 Prometheus feedback LLM까지 켠 full 구성” 기준으로 맞습니다. 반대로 현재 direct 벤치마크의 실제 생성 경로만 보면 루브릭 Q별 LLM 호출이 빠지므로 4회보다도 적게, 보통 1~2회 생성 호출로 끝납니다.

### Q. 왜 LLM 호출이 여러 번인데 생각보다 오래 안 걸릴 수 있나요?

평가 prompt는 답변 생성 prompt보다 짧고, 재생성은 저점 case에서만 발생하며, ARES는 통합 judge로 호출 수를 줄였기 때문입니다. 특히 현재 direct 벤치마크에서는 Civil LLM-Rubric이 Q별 LLM judge를 호출하지 않는 경로라서 19회 full 구성보다 훨씬 가볍습니다. 또 일부 문제는 rule fallback이나 후처리로 처리됩니다.

### Q. Chroma DB가 비어 있거나 검색 결과가 0개면 어떻게 되나요?

근거 없는 답변을 막기 위해 실패 또는 fallback으로 처리합니다. 이때 `derived_query`, collection, top_k, filters, routing_trace를 확인해야 합니다.

### Q. 법령 데이터가 들어왔는데 답변에 법령이 안 보일 수 있나요?

가능합니다. 법령 데이터가 저장되어 있어도 검색 결과에 법령 context가 잡히지 않거나, 답변 prompt에 반영되지 않거나, 법령 grounding이 실패하면 최종 답변에 법령이 직접 나타나지 않을 수 있습니다. 따라서 `legal_grounding_status`, `legal_citations`, 검색 context를 함께 확인해야 합니다.

### Q. parse_success가 낮은데 postprocess_success가 높으면 괜찮은 건가요?

모델 원본 JSON은 많이 깨졌지만 후처리로 사용자에게 보여줄 답변을 복구했다는 뜻입니다. 운영 안정성에는 도움이 되지만, 장기적으로는 prompt와 모델 출력 형식을 더 안정화해야 합니다.

### Q. 현재 평가가 객관적으로 믿을 수 있는 점수냐고 물으면 뭐라고 답하나요?

완전한 객관 점수라고 말하면 안 됩니다. 대신 기준이 문서화되어 있고, 같은 dataset/config/model 조건에서 재현 가능하며, Rubric과 ARES가 서로 다른 관점으로 평가하고, citation/context/unsupported claim/missing segment 같은 근거 로그가 함께 남기 때문에 감사 가능한 자동 평가 지표라고 답하면 됩니다. 최종적으로 고위험 case는 사람 검토 샘플로 확인하므로 자동 점수와 수동 판단을 함께 쓰는 구조입니다.

## 11. 발표나 리뷰에서 조심해야 할 표현

아래 표현은 피하는 것이 좋습니다.

- “모델 튜닝을 했다”
  - 실제로는 prompt, retrieval, postprocess, evaluation pipeline 개선입니다.
- “ARES 논문 전체를 재현했다”
  - 현재는 프로젝트 목적에 맞춘 ARES-lite 또는 LLM judge 기반 진단입니다.
- “Rubric이 사람 평가를 완전히 대체한다”
  - Rubric은 자동 품질 신호이고, 고위험 case는 사람 검토가 필요합니다.
- “citation match가 높으니 답변이 사실적으로 완벽하다”
  - citation match는 형식 검증입니다. 의미적 근거성은 별도 평가가 필요합니다.
- “Prometheus가 답변을 무조건 개선한다”
  - 개선 후보를 만들고, 재평가 후 채택 여부를 결정합니다.

## 12. 파일 위치 빠른 참조

| 기능 | 주요 파일 |
|---|---|
| PromptFactory | `app/generation/prompts/prompt_factory.py` |
| GenerationService | `app/generation/service.py` |
| API generation router | `app/api/routers/generation.py` |
| direct benchmark | `scripts/Be3_run_week6_model_benchmark.py` |
| Civil LLM-Rubric | `app/evaluation/civil_llm_rubric.py` |
| Prometheus feedback | `app/evaluation/prometheus_feedback.py` |
| ARES-lite evaluator | `app/evaluation/ares_lite/evaluator.py` |
| ARES prompt | `app/evaluation/ares_lite/prompts.py` |
| Rubric 문서 | `docs/40_delivery/week11/llm_evaluation/Civil_Complaint_LLM_Rubric.md` |
| ARES 문서 | `docs/40_delivery/week11/llm_evaluation/ares.md` |
| Prometheus 문서 | `docs/40_delivery/week11/llm_evaluation/Prometheus.md` |
| benchmark comparison | `docs/40_delivery/week11/benchmark_report/` |

## 13. 용어 정리

| 용어 | 의미 |
|---|---|
| `derived_query` | 민원 내용에서 검색용으로 추출·정리한 query |
| `routing_trace` | 어떤 topic/complexity/route로 처리됐는지 남기는 추적 정보 |
| context | Chroma DB 등에서 가져온 답변 근거 chunk |
| citation | 답변 주장을 뒷받침하는 context 근거 참조 |
| strict citation match | citation이 실제 context chunk와 형식적으로 정확히 맞는지 보는 지표 |
| repaired citation | 모델 citation이 불완전할 때 후처리로 context와 다시 맞춘 citation |
| `fallback_used` | 기본 생성 또는 파싱이 실패해 보조 경로를 사용했는지 |
| `postprocess_success_rate` | 후처리 이후 사용 가능한 답변으로 복구된 비율 |
| `safety_cap` | 위험 답변의 최종 점수를 일정 이상 못 올라가게 제한하는 장치 |
| `human_review_required` | 자동 평가만으로 통과시키기 어려운 수동 검토 대상 |
| low_score_items | Rubric에서 낮게 나온 항목 목록 |
| Prometheus revision | 낮은 항목을 바탕으로 만든 개선 답변 |
| ARES risk_level | 검색·근거·질의대응 관점의 위험 수준 |

## 14. 한 문장으로 설명하기

- PromptFactory: “모든 생성 경로가 같은 규칙으로 prompt를 만들게 하는 단일 진입점입니다.”
- Civil LLM-Rubric: “최종 민원 회신 품질을 Q0~Q7로 채점하는 평가기입니다.”
- Prometheus: “낮은 평가 항목을 바탕으로 답변을 한 번 더 고치게 하는 피드백 재생성 장치입니다.”
- ARES-lite: “검색 context와 답변의 근거성, 관련성, 누락 여부를 진단하는 RAG 평가기입니다.”
- 전체 BE3 평가 파이프라인: “좋은 답변을 만들고, 왜 안 좋은지까지 추적하기 위한 생성-평가-개선-진단 흐름입니다.”
