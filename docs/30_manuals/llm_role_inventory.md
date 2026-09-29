# LLM 사용 지점 — 모델 교체 전 기준선 조사

> 이전 비교 기록. 현재 두 모델 선정·설정은 [후속 보고서](llm_two_model_selection.md)를 따른다.

기준: 2026-09-29, K6 인도 커밋 이후 코드와 로컬 설정. **새 모델 선정 전 조사 기록**이며, 이후 교체 결과·최종 설정은 별도 비교 결과 문서를 따른다. 호출 성공이나 모델 크기를 정확도 근거로 해석하지 않는다.

## 설정 공유 범위

| 설정 | 조사 시 실제 값 | 공유 역할 |
| --- | --- | --- |
| `OLLAMA_MODEL` | `exaone3.5:7.8b` | 민원 생성·피드백·재작성, K6 Local, 선택적 담당부서 LLM 재랭킹; 별도 모델 미지정 검색 필터 |
| `STRUCTURING_MODEL` | `exaone3.5:7.8b` (기본값) | 민원 구조화·선택적 자기검증, K3 분석·설계·수정, K4 모델 추출; 요청 분리 모델 기본값 |
| `CIVIL_LLM_RUBRIC_MODEL` | `qwen3.5:4b` | 민원 Q0~Q7 평가, K3 반례 검토 |
| `GROUNDING_FILTER_MODEL` | `exaone3.5:7.8b` | 검색 API 근거 관련성 필터. 빈 값이면 `OLLAMA_MODEL` 사용 |
| `REQUEST_SEGMENT_LLM_MODEL` | `exaone3.5:7.8b` (기본값) | 비활성 요청 분리 보조 |
| `PUBLIC_INSIGHT_LLM_MODEL` | `exaone3.5:7.8b` | 공공이슈 인사이트. 현재 `provider=fake`이므로 실제 Ollama 호출 안 함 |

공통 설정은 [config.py](../../app/core/config.py), 설치 예시는 [.env.example](../../.env.example)을 따른다. 로컬 `.env` 값과 코드 기본값은 다르다. 생성 출력/context의 코드 기본값은 **640/2048**, 조사 시 로컬 설정은 **1536/8192**이다. 이번 조사에서 비밀값·개인 경로는 기록하지 않았다.

## 활성 호출 경로

예산 표기는 `최대 출력 토큰 / context 토큰`이다. `think 미지정`은 비추론 보장이 아니라 모델/Ollama 기본 동작을 따른다는 뜻이다. timeout은 별도 표기가 없으면 `OLLAMA_TIMEOUT=120초`다.

| 역할·호출부 | 프롬프트·API | 예산·추론 설정 | 재시도·후속 흐름 |
| --- | --- | --- | --- |
| 민원 답변 — [generation/service.py](../../app/generation/service.py) `generate_qa` | 기존 RAG 프롬프트·인용 계약, `/api/generate` | 로컬1536/8192, think 미지정, temp0.2 | 파싱 실패시 compact 프롬프트/temp0으로 최대1회 재시도 |
| 피드백·재작성 — [generation.py](../../app/api/routers/generation.py) `_maybe_apply_prometheus_revision`, [prometheus_feedback.py](../../app/evaluation/prometheus_feedback.py) | 평가 저점수 항목 기반 피드백 및 수정 프롬프트, `/api/generate` | 로컬1536/8192, think 미지정, temp0 | 저점수일 때 피드백1회+재작성1회. 수정 답변 평가 후 추가 수정 루프 없음 |
| 민원 평가 — [civil_llm_rubric.py](../../app/evaluation/civil_llm_rubric.py), `GenerationService.call_rubric_judge` | **Q2 / Q3·Q4·Q5 / Q1·Q7 / Q6 / Q0의 5회**, 항목 정의·선택지 유지, `/api/generate` | 근거그룹1536/8192, 표현그룹640/8192, 단독192/8192; think=false, temp0 | 민원·검색 근거가 같은 요청 내 Q2 캐시. 재작성 후 나머지4회 평가. Q0는 다른 평가 결과 없이 독립 입력 |
| 민원 구조화 — [service.py](../../app/structuring/service.py), [structured_extractor.py](../../app/structuring/structured_extractor.py) | **`STRUCTURING_CONSTRAINED=true`**, 관찰·결과·요청·맥락/주체와 근거 범위를 스키마 제약으로 추출, `/api/chat` | 512/4096, 입력 최대2000자, timeout90초, think 미지정, temp0.1 | 파싱·검증 실패시 강화 프롬프트/temp0으로1회 재시도. 실패시 기존 폴백 |
| K3 분석·설계·수정 — [ontology_run.py](../../app/knowledge/ontology_run.py) | `COMMON/ANALYZE/DESIGN`, 동결 블록·CQ·기준 정의, `/api/generate` | 분석2048/16384, 설계·수정4096/32768, think 미지정, temp0 | 분석n+설계1+검토1. 필요시 수정1, 수정 후 AI 재검토 없음 |
| K3 반례 검토 — 같은 파일 `REVIEW` | 개념/개체·범위·관계·근거·누락 비교, `/api/generate` | 2048/32768, think=false, temp0 | 실패는 단계 실패. 성공 단계 재사용하며 수동 재시도; 모델·프롬프트·예산 변경시 새 실행 필요 |
| K4 추출 — [extraction.py](../../app/knowledge/extraction.py), [extraction_contract.py](../../app/knowledge/extraction_contract.py) | 온톨로지·허용 개체·블록에 연결한 사실 추출, `/api/generate` | 4096/32768, think 미지정, temp0 | 성공 단위 재사용, 실패 단위 재시도. **CSV 매핑·PDF 규칙 추출은 모델 호출0**. 모델 교체 비교에는 HTML/general 모델 단위를 포함해야 함 |
| K6 Local — [search.py](../../app/knowledge/search.py), [search_answer.py](../../app/knowledge/search_answer.py) | 공개 A는 사실 그룹 선택 후 서버 원값 표시. B/C/D는 내부 비교용, `/api/generate` | 1536/16384, Qwen 이름이면 think=false; 명시적 추론 실험3072/16384 | 기본1회, 자동 평가·재작성·재시도 없음. 실험 후보를 공개 기본값으로 자동 채택하지 않음 |
| 검색 근거 필터 — [grounding_filter.py](../../app/retrieval/grounding_filter.py), [retrieval.py](../../app/api/routers/retrieval.py) | 민원-후보 쟁점 관련성0/1/2점, `/api/generate` | 배치max(24,4×후보수+12)/3072; 개별24/2048, think 미지정, temp0 | 배치 실패시 개별 채점. 전역 `GROUNDING_FILTER_ENABLED=false`여도 **검색API는 true 명시**. 민원 생성의 내부 재검색은 false 명시 |

K3·K4·K6는 선택적 메타데이터 반환으로 `done_reason=length` 등을 확인한다. 일반 생성·구조화는 동일한 메타데이터 처리를 사용하지 않는다. 공통 `call_ollama()`의 기본 반환 계약은 문자열이다.

## 선택 기능·비활성 경로

| 기능 | 조사 시 상태 | 호출부·설정 |
| --- | --- | --- |
| 요청 분리 보조 | **off**, provider=none. 규칙 분리 사용 | [request_segment_analysis.py](../../app/retrieval/analyzers/request_segment_analysis.py), [request_segment_hybrid.py](../../app/retrieval/analyzers/request_segment_hybrid.py). generate JSON, text512 또는block256/context4096, timeout30초, think 미지정. shadow는 관측만, assist는 검증·정책 통과시 교체 |
| legacy 4요소 구조화 | constrained=false일 때만 사용 | [llm_extractor.py](../../app/structuring/llm_extractor.py). chat JSON,512/4096, 파싱 실패 강화 프롬프트1회. 현행 활성 추출기와 구분 |
| 구조화 자기검증 | `ENABLE_SELF_VERIFY=false` | [verifier.py](../../app/structuring/verifier.py). STRUCTURING_MODEL, chat 출력256, think 미지정 |
| 담당부서 LLM 재랭킹 | `ENABLE_RESPONSIBLE_UNIT=false`, `RESPONSIBLE_UNIT_USE_LLM=false` | [department_assigner.py](../../app/structuring/department_assigner.py). OLLAMA_MODEL, chat 출력512, think/context 미지정. 실패시 기존 검색 결과 유지 |
| 공공이슈 인사이트 | enabled=true, **provider=fake** | [llm_provider.py](../../app/complaint_intelligence/public_insights/llm_provider.py). 실 provider는 generate/chat 지원; 로컬1024/4096, timeout180초, think 미지정, action retry=false. 모델명 값이 있다는 이유로 활성 LLM으로 집계하지 않음 |
| 검색 파이프라인의 LLM 필터 | 선택한 파이프라인에 따라 실행 | [llm_relevance_filter.py](../../app/retrieval/pipeline/stages/llm_relevance_filter.py). 별도 모델 미지정시 OLLAMA_MODEL, 공통 grounding 코어 사용 |

## 요청 분리의 확인된 실패와 비교 입력

기존 `reports/request_segment_llm_condition_b_shadow_100.json`의 **501472**를 현행 규칙으로 재실행했다. 원문에는 ①월64시간 근무시4대보험 신고 여부, ②근로계약 근무기간 표기 방식의 차이라는 두 질문이 있으나 규칙 결과는②만 남겼다. 저장된 이전 LLM 답변이나 과거 검수 라벨을 정답으로 삼지 않고 명시적 원문 질문을 기준으로 확인했다.

보조 비교 입력은 `data/model_role_comparison_20260929/aux_cases.json`에 고정했다. 요청 분리1사례와 검색 관련성 배치1회(동일 민원/다른 쟁점2문서)이며 기존 prompt builder를 사용한다. 분리 사례 개선은 **단순 모델 교체와 assist 활성화의 근거를 분리**해 판단해야 한다. 작은 비교가 광범위한 활성화를 정당화하지 않는다.

## 오프라인 직접 모델명·별도 호출

`app/evaluation/ares_lite`의 별도·통합 판정기는 호출 함수를 주입받는 오프라인 평가 경로다. 현재 API·생성·지식 서비스에서 연결한 호출은 확인되지 않았다.

서비스 설정 변경으로 아래 실험값을 일괄 치환하지 않는다. 실행 전 해당 스크립트의 모델·endpoint를 따로 확인한다.

- `scripts/judge_fair_pool.py`, `relabel_new_qrels_v3.py`, `expand_qrels_from_reranker.py`: EXAONE3.5/Gemma3 직접 지정.
- `scripts/judge_pool_qwen.py`, 관련3judge/spotcheck 스크립트: Qwen2.5:14b 등 별도 채점 모델 및 과거 원격 Ollama 기본 주소.
- `scripts/cross_validate_qrels_v3_local.py`, `expand_v3_queries.py`, `validate_new_qrels.py`: EXAONE3.5/Gemma3/ax4-light-local 직접 지정. 일부는 Ollama Python client의 `chat` 호출.
- `scripts/judge_exaone.py`: `JUDGE_MODEL` 별도 설정, 기본 EXAONE. `run_week3_model_benchmark.py`, `be1_run_week3_model_benchmark.py`, `Be3_run_week6_model_benchmark.py`: CLI 비교 모델과 직접 HTTP 호출.
- `scripts/collect_request_segment_strict_allow.py`, `evaluate_request_segment_pregate_shadow.py`: 별도 CLI 모델·예산으로 요청 분리 실험.
- `scripts/measure_*`, `eval_*`, `run_raw_dataset_qa.py`, `compare_knowledge_k6_answers.py`: 공통 서비스 또는 직접 Ollama를 이용한 오프라인 비교. K6 비교 스크립트의 chat 어댑터는 진단용이며 서비스 호출 API가 아님.

조사한 `app/`·`src/` 서비스 코드에서 별도 OpenAI/Anthropic 생성 호출은 확인되지 않았다. 임베딩·CrossEncoder 리랭커·긴급도 분류기는 이 생성 LLM 교체 범위와 구분한다.

## 해석과 다음 작업

공유 설정 하나를 바꾸면 미평가 역할도 함께 바뀐다. 역할별 비교 결과가 다를 때만 최소 설정 분리를 적용해야 한다. 특히 think 생략, 구조화 기존2000자 절단, 검색 필터의 짧은 출력 한도를 새 모델에서 그대로 안전하다고 가정하면 안 된다. 필요한 역할만 호환성·예산을 확인하며 원문을 추가로 조용히 잘라 실패를 숨기지 않는다.

이 문서는 호출 경로·설정과 규칙 분리 실패를 확인한 기록이지 모델 품질 평가 결과가 아니다. 다음은 고정 입력에서 기존·신규 모델을 비교하고 실제 개선이 확인된 역할만 반영하는 작업이다. 현재 이 조사에 사용자 결정이 필요한 사항 없음.
