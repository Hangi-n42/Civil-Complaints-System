# PRD: FR-4 Generation 모듈 고도화
**문서 버전:** v1.0  
**작성일:** 2026-06-02  
**작성자:** (Senior TPM)  
**상태:** 초안(Draft) — 검토 요청  
**관련 모듈:** FR-3 Retrieval, FR-4 Generation  

---

## 목차

1. [배경 및 현황 분석](#1-배경-및-현황-분석)
2. [문제 정의](#2-문제-정의)
3. [목표 및 성공 지표 (KPI)](#3-목표-및-성공-지표-kpi)
4. [사용자 스토리](#4-사용자-스토리)
5. [기능 요구사항](#5-기능-요구사항)
6. [비기능 요구사항](#6-비기능-요구사항)
7. [시스템 아키텍처 변경 사항](#7-시스템-아키텍처-변경-사항)
8. [인터페이스 명세](#8-인터페이스-명세)
9. [예외 처리 및 엣지 케이스](#9-예외-처리-및-엣지-케이스)
10. [마이그레이션 계획](#10-마이그레이션-계획)
11. [의존성 및 리스크](#11-의존성-및-리스크)
12. [출시 범위 및 단계 계획 (Phasing)](#12-출시-범위-및-단계-계획-phasing)

---

## 1. 배경 및 현황 분석

### 1.1 현재 시스템 구조

현재 FR-4 Generation 모듈은 다음 컴포넌트로 구성되어 있다.

| 컴포넌트 | 구현체 | 역할 |
|---|---|---|
| LLM Caller | `GenerationService.call_ollama()` | Ollama API 단일 호출 |
| Prompt Builder | `PromptFactory` | topic_type별 프롬프트 구성 |
| JSON Parser | `parse_qa_json_response()` | LLM 출력 → JSON 파싱 + 재시도 |
| Citation Mapper | `citation_mapper.py` | 근거 문서 → citation 객체 매핑 |
| Response Normalizer | `normalize_response()` | unified schema 변환 |
| Validator | `qa_response_validator.py` | citation token 검증 |

**현재 Ollama 호출 파라미터:**

```python
payload = {
    "model": settings.OLLAMA_MODEL,
    "prompt": prompt,
    "stream": False,
    "format": "json",          # ← JSON 즉시 강제
    "options": {
        "temperature": 0.7,
        "num_predict": 128,    # ← 최대 128 토큰 (매우 제한적)
        "num_ctx": 1024,       # ← 컨텍스트 1K (검색 결과 소실 위험)
    },
}
```

**현재 응답 스키마 (`normalize_response` 기준):**

```python
{
    "routing_trace": {...},
    "structured_output": {
        "summary": str,
        "action_items": List[str],
        "request_segments": List[str],
    },
    "answer": str,
    "citations": List[{"doc_id", "source", "quote"}],
    "limitations": List[str],
    "latency_ms": {"analyzer", "router", "retrieval", "generation"},
    "quality_signals": {
        "citation_coverage": float,
        "hallucination_flag": bool,
        "segment_coverage": float,
    },
}
```

### 1.2 데이터 기반 현황 진단

VOC(Voice of Customer) 및 품질 평가 데이터 분석 결과:

| 문제 구분 | 측정값 | 기준 |
|---|---|---|
| JSON 파싱 실패율 (재시도 포함) | 14.7% | 목표 ≤ 2% |
| Hallucination 발생률 (검색 근거 미포함 사실 생성) | 18.3% | 목표 ≤ 5% |
| Citation Coverage (답변 내 출처 인용 비율) | 0.41 | 목표 ≥ 0.80 |
| 복합 민원(complexity=high) 답변 완결성 | 0.54 | 목표 ≥ 0.80 |
| num_predict=128로 인한 답변 중도 truncation | 22% | 목표 0% |
| Generation P95 지연 | 4,200ms | 목표 ≤ 2,500ms |

### 1.3 근본 원인 분석

**[원인 A] JSON 즉시 강제(`"format": "json"`)로 인한 reasoning 품질 저하**  
Ollama의 `"format": "json"` 옵션은 모델이 첫 토큰부터 JSON 구조에 맞는 출력을 생성하도록 강제한다. 이는 chain-of-thought 추론이 완료되기 전에 `"answer"` 필드를 emit하게 만들어 추론 품질을 저하시킨다. EMNLP 2024 연구(SLOT 논문)에서 이 방식이 추론 정확도를 최대 27%p 저하시킴이 실증적으로 확인되었다.

**[원인 B] num_predict=128의 과소 설정**  
민원 답변은 법령 조항 인용, 처리 절차, 담당 부서 안내 등 평균 200-350 토큰 이상의 텍스트를 필요로 한다. 현재 128 토큰 제한으로 22%의 답변이 중도 truncation되어 불완전한 응답이 제공되고 있다.

**[원인 C] 검색 결과와 생성 내용의 grounding 미검증**  
현재 `qa_response_validator.py`는 `[[출처 N]]` 토큰의 형식만 검증하고, 실제로 답변 내용이 검색된 근거 문서에 기반하는지(faithfulness)를 검증하지 않는다. 이로 인해 모델이 파라메트릭 지식(학습 데이터)에서 사실을 생성하는 hallucination이 탐지되지 않은 채 응답에 포함된다.

**[원인 D] 복합 민원의 증거 누락 미감지**  
complexity=high 질의에서 검색된 문서가 민원의 모든 하위 질문(sub-question)을 커버하는지 생성 전에 확인하지 않는다. 이로 인해 일부 sub-question에 대한 근거가 없는 상태에서 답변이 생성되어 완결성이 낮아진다.

---

## 2. 문제 정의

### Problem Statement

> 현재 FR-4 Generation 모듈은 단일 Ollama 호출에 JSON 출력을 즉시 강제하는 구조로, (1) 추론 전에 구조화 출력을 강제하여 답변 품질이 저하되고, (2) 검색 근거와 생성 내용 간의 faithfulness를 검증하지 않아 hallucination이 탐지되지 않으며, (3) 복합 민원에서 증거 누락 시 불완전한 답변이 그대로 반환되는 한계가 있다.

### 해결 방향

- **2단계 생성 분리(SLOT 방식):** reasoning phase(`<think>`)와 structured output phase를 분리하여, 추론 완료 후 JSON을 생성한다.
- **증거 갭 분석(FAIR-RAG SEA 방식):** 생성 전에 검색 결과가 모든 sub-question을 커버하는지 평가하고, 누락 시 보완 검색을 트리거한다.
- **Faithfulness 검증:** 생성된 답변의 각 사실 주장이 검색 근거 문서에 실제로 존재하는지 검증하고 `hallucination_flag`를 정밀화한다.

---

## 3. 목표 및 성공 지표 (KPI)

### 3.1 정량적 목표

| 지표 | 현재값 | 목표값 | 측정 방법 |
|---|---|---|---|
| **JSON 파싱 실패율** | 14.7% | **≤ 2%** | 운영 에러 로그 |
| **Hallucination 발생률** | 18.3% | **≤ 5%** | NLI 기반 faithfulness 평가 |
| **Citation Coverage** | 0.41 | **≥ 0.80** | quality_signals.citation_coverage |
| **복합 민원 답변 완결성** | 0.54 | **≥ 0.80** | eval_set_v1 human evaluation |
| **답변 truncation 비율** | 22% | **0%** | `finish_reason` 모니터링 |
| **Generation P95 지연** | 4,200ms | **≤ 2,500ms** | APM |
| **Evidence Gap 탐지율** | — | **≥ 85%** | 갭 주입 테스트셋 기준 |

### 3.2 정성적 목표

- 모든 답변에 `[[출처 N]]` 형식의 citation이 1개 이상 포함된다.
- `quality_signals.hallucination_flag`가 실제 hallucination과 85% 이상 일치한다.
- 단계별 latency(`reasoning_ms`, `structured_output_ms`, `sea_ms`)가 `latency_ms`에 분해되어 디버깅 가능하다.

---

## 4. 사용자 스토리

### 4.1 최종 사용자 (민원 처리 공무원)

```
As 민원 처리 공무원,
I want 복합 민원에 대한 답변이 각 하위 질문별로 출처를 명시하고,
       근거가 없는 경우 "해당 정보를 확인할 수 없습니다"로 안내받기를 원한다.
So that 법적 근거 없는 정보로 민원인을 오안내하는 사고를 방지할 수 있다.
```

```
As 민원 처리 공무원,
I want 답변이 항상 완전한 문장으로 종결되기를 원한다.
So that 처리 결과 문서에 그대로 활용할 수 있다.
```

### 4.2 서비스 품질 관리자

```
As 서비스 품질 관리자,
I want hallucination_flag=true인 응답의 비율을 일 단위로 모니터링하고,
       5%를 초과하면 알림을 받기 원한다.
So that 서비스 신뢰도 저하를 조기에 감지할 수 있다.
```

### 4.3 개발자

```
As 백엔드 개발자,
I want generation_trace에서 reasoning 단계의 think 텍스트, SEA 평가 결과,
       각 단계별 latency를 확인할 수 있기를 원한다.
So that 답변 품질 이슈 발생 시 어느 단계에서 문제가 발생했는지 즉시 파악할 수 있다.
```

---

## 5. 기능 요구사항

### FR4-F01: 2단계 생성 파이프라인 (SLOT 방식)

**설명:** 현재의 단일 Ollama 호출을 Reasoning Phase와 Structured Output Phase 두 단계로 분리한다.

**FR4-F01-1: Phase 1 — Reasoning (Think)**
- `"format": "json"` 옵션을 제거한다.
- 프롬프트: `[System] + [Evidence Chain] + [Question] + <think> 자유롭게 추론하세요 </think>`
- LLM이 `<think>...</think>` 태그 내에서 자유로운 chain-of-thought 추론을 수행한다.
- 출력: reasoning 텍스트 (비구조화)
- 파라미터:
  ```python
  {
      "temperature": 0.7,
      "num_predict": 512,   # 충분한 reasoning 공간 확보
      "num_ctx": 4096,      # 검색 결과 전체 포함 가능
  }
  ```

**FR4-F01-2: Phase 2 — Structured Output**
- Phase 1의 reasoning 결과를 conditioning으로 활용한다.
- 프롬프트: `[Phase 1 reasoning] + [아래 JSON 형식으로 답변을 작성하세요]`
- `"format": "json"` 옵션은 이 단계에서만 적용한다.
- reasoning이 이미 완료된 상태에서 구조화하므로 truncation 없이 완전한 JSON 생성이 보장된다.
- 파라미터:
  ```python
  {
      "temperature": 0.1,   # 구조화 단계에서는 낮은 temperature
      "num_predict": 1024,  # 완전한 JSON 출력 보장
      "num_ctx": 4096,
      "format": "json",
  }
  ```

**수용 기준:**
- Phase 1 출력에 `<think>` 태그가 반드시 포함된다.
- Phase 2 출력이 valid JSON으로 파싱 성공률 ≥ 98%.
- 두 Phase의 Ollama 호출은 동일한 `GenerationService` 인스턴스에서 순차 실행된다.
- `generation_trace`에 `phase1_think`, `phase2_json_raw`, `phase1_latency_ms`, `phase2_latency_ms`가 기록된다.

---

### FR4-F02: 증거 갭 분석 모듈 (FAIR-RAG SEA 방식)

**설명:** Generation 실행 전, 검색된 문서가 질의의 모든 sub-question을 커버하는지 평가하는 Structured Evidence Assessment(SEA) 모듈을 추가한다.

**FR4-F02-1: Sub-question 추출**
- FR-1 Analyzer의 `complexity_trace.intent_count`와 `request_segments`를 활용한다.
- complexity=high이고 `intent_count ≥ 2`인 경우에만 SEA를 실행한다.
- complexity=low/medium은 SEA를 건너뛰고 바로 Generation을 실행한다. (지연 최소화)

**FR4-F02-2: 커버리지 평가**
- 각 sub-question에 대해 검색된 passages 중 관련 내용이 있는지 확인한다.
- 평가 방식: 키워드 overlap + 간단한 NLI 분류 (2-class: entail/not_entail)
- NLI 모델: `snunlp/KR-FinBert-SC` 또는 경량 cross-encoder (로컬 실행)
- 커버리지 임계값: `sea_coverage_threshold = 0.6` (설정 가능)

**FR4-F02-3: 갭 감지 시 보완 검색 트리거**
- 커버리지 < 임계값인 sub-question이 존재하는 경우:
  - FR-3 Retrieval에 `supplementary_query`를 전송한다.
  - 보완 검색은 최대 1회로 제한한다. (무한 루프 방지)
  - 보완 검색 결과를 기존 passages에 병합하여 Generation을 실행한다.
- 보완 검색 후에도 커버리지 부족 시: `limitations`에 해당 sub-question을 "확인 불가" 항목으로 추가한다.

**FR4-F02-4: SEA 출력 스키마**

```python
@dataclass
class SEAResult:
    is_complete: bool
    coverage_scores: Dict[str, float]      # {sub_question: coverage_score}
    gap_sub_questions: List[str]           # 커버리지 부족 sub-question 목록
    supplementary_triggered: bool
    sea_latency_ms: float
```

**수용 기준:**
- SEA 모듈 실행 시간 P95 ≤ 200ms (NLI 포함)
- 갭 주입 테스트셋 기준 탐지율 ≥ 85%
- SEA 결과가 `generation_trace.sea_result`에 기록된다.

---

### FR4-F03: Faithfulness 검증 강화

**설명:** 현재 형식 기반(citation token 존재 여부) 검증에서, 생성 내용이 실제 검색 근거에 기반하는지를 검증하는 semantic faithfulness 검증으로 고도화한다.

**FR4-F03-1: Claim 추출**
- Phase 1 reasoning 또는 Phase 2 answer에서 사실 주장(factual claim)을 추출한다.
- 추출 방식: 마침표/문장 단위 분리 후 동사+명사 패턴 필터링

**FR4-F03-2: Claim-Evidence 검증**
- 각 claim에 대해 검색된 passages 중 entailment 관계인 것이 존재하는지 확인한다.
- NLI 모델: SEA와 동일 모델 재사용 (지연 최소화)
- 미지원 claim (어떤 passage와도 entailment 관계 없음) → `hallucination_candidate`로 마킹

**FR4-F03-3: quality_signals 고도화**

```python
# 기존
"quality_signals": {
    "citation_coverage": float,
    "hallucination_flag": bool,
    "segment_coverage": float,
}

# 개선
"quality_signals": {
    "citation_coverage": float,        # 기존 유지
    "hallucination_flag": bool,        # 기존 유지 (faithful_ratio < 0.7이면 True)
    "segment_coverage": float,         # 기존 유지
    "faithful_ratio": float,           # ← 신규: supported_claims / total_claims
    "unsupported_claims": List[str],   # ← 신규: hallucination 의심 주장 목록
    "sea_coverage": float,             # ← 신규: SEA 평균 커버리지 점수
}
```

**수용 기준:**
- `faithful_ratio` 계산 오버헤드 P95 ≤ 150ms
- `hallucination_flag`가 실제 hallucination과 ≥ 85% 일치 (평가 데이터셋 기준)

---

### FR4-F04: PromptFactory 개선

**설명:** 현재 단일 프롬프트를 Phase 1 (reasoning)과 Phase 2 (structured output) 두 가지 프롬프트로 분리한다.

**FR4-F04-1: Phase 1 Prompt (topic-aware reasoning)**

```
[System]
당신은 대한민국 지방자치단체의 {topic_type} 분야 민원을 처리하는 전문 AI 어시스턴트입니다.

[Evidence Chain]
{evidence_chain}  ← 검색 결과 + DCI trajectory 포함

[Question]
{question}

<think>
위 근거 문서들을 바탕으로 다음을 단계적으로 분석하세요:
1. 질의의 핵심 요청 사항을 파악하세요.
2. 각 근거 문서가 어떤 하위 질문에 답하는지 정리하세요.
3. 답변에 포함해야 할 핵심 사실과 출처를 식별하세요.
4. 근거가 없는 부분을 명시하세요.
</think>
```

**FR4-F04-2: Phase 2 Prompt (structured output)**

```
[Phase 1 Reasoning]
{phase1_reasoning}

위 분석을 바탕으로 아래 JSON 형식으로 최종 답변을 작성하세요.
출처 인용은 반드시 [[출처 N]] 형식을 사용하고, 근거 없는 내용은 포함하지 마세요.

{json_schema}
```

**FR4-F04-3: Evidence Chain 구성 규칙**

| 검색 경로 | Evidence Chain 구성 방식 |
|---|---|
| Hybrid 경로 | 상위 top_k 문서의 snippet을 순위별로 나열 |
| DCI 경로 | `[Step N] 검색 명령: {command}\n근거: {observation}` 형식으로 trajectory 포함 |
| 혼합 (보완 검색 있음) | DCI trajectory 먼저, 보완 Hybrid 결과 후에 추가 |

---

### FR4-F05: Generation Trace 로깅 확장

**설명:** 현재 `latency_ms.generation` 단일 값에서, 단계별 상세 trace로 확장한다.

```python
# generation_trace 스키마
{
    "generation_path": "two_phase" | "single_phase",
    
    # Phase 1
    "phase1_think": str,               # reasoning 전체 텍스트
    "phase1_latency_ms": float,
    "phase1_token_count": int,
    
    # SEA
    "sea_result": {
        "is_complete": bool,
        "coverage_scores": {"sub_q_1": 0.85, "sub_q_2": 0.42},
        "gap_sub_questions": ["sub_q_2"],
        "supplementary_triggered": True,
        "sea_latency_ms": 88.3,
    },
    
    # Phase 2
    "phase2_json_raw": str,            # raw JSON 텍스트
    "phase2_latency_ms": float,
    "phase2_token_count": int,
    
    # Faithfulness
    "faithfulness_result": {
        "faithful_ratio": 0.83,
        "unsupported_claims": ["..."],
        "faithfulness_latency_ms": 62.1,
    },
    
    # 전체
    "total_generation_latency_ms": float,
    "retry_count": int,
}
```

---

## 6. 비기능 요구사항

### 6.1 성능

| 항목 | 요구 사항 |
|---|---|
| Generation 전체 P95 지연 | ≤ 2,500ms (Phase 1 + SEA + Phase 2 + Faithfulness) |
| Phase 1 (Reasoning) P95 | ≤ 1,200ms |
| SEA 모듈 P95 | ≤ 200ms |
| Phase 2 (Structured Output) P95 | ≤ 800ms |
| Faithfulness 검증 P95 | ≤ 150ms |
| complexity=low/medium (SEA 없음) P95 | ≤ 1,800ms |

### 6.2 안정성

| 항목 | 요구 사항 |
|---|---|
| Phase 1 실패 시 | Phase 2로 직행 (reasoning 없이), 경고 로그 |
| SEA 모듈 오류 시 | SEA 건너뛰고 Generation 실행, `sea_result.error: true` 기록 |
| Phase 2 JSON 파싱 실패 시 | 최대 2회 재시도, 모두 실패 시 `GenerationError(code="PROCESSING_ERROR")` |
| Faithfulness 모델 오류 시 | 검증 생략, `faithful_ratio: null` 기록, 서비스 계속 |
| Ollama 연결 실패 시 | 기존 에러 핸들링 유지 (MODEL_NOT_READY, MODEL_TIMEOUT) |
| 가용성 | 월 99.5% 이상 |

### 6.3 일관성 (Backward Compatibility)

| 항목 | 요구 사항 |
|---|---|
| `normalize_response()` 출력 스키마 | **변경 없음** (기존 6개 최상위 키 유지) |
| `quality_signals` 기존 필드 | 유지 (citation_coverage, hallucination_flag, segment_coverage) |
| API 엔드포인트 시그니처 | 변경 없음 |
| citation 형식 `[[출처 N]]` | 유지 |

### 6.4 관측 가능성

| 항목 | 요구 사항 |
|---|---|
| 메트릭 | `generation_phase1_latency_ms`, `generation_sea_latency_ms`, `generation_phase2_latency_ms`, `hallucination_flag_rate`, `json_parse_failure_total` |
| 알림 | `json_parse_failure_rate > 3%` 또는 `hallucination_flag_rate > 8%` 시 알림 |
| 로그 | `generation_trace` 전체를 구조화 JSON으로 기록 (PII 마스킹 적용) |

---

## 7. 시스템 아키텍처 변경 사항

### 7.1 현재 아키텍처

```
Retrieval 결과
    └── GenerationService.generate()
          ├── PromptFactory.build_prompt()
          ├── call_ollama(format=json, num_predict=128)
          ├── parse_qa_json_response()   ← 파싱 실패 시 재시도
          ├── citation_mapper()
          └── normalize_response()
```

### 7.2 목표 아키텍처

```
Retrieval 결과
    └── GenerationService.generate()
          │
          ├── [complexity=high] SEAModule.assess()
          │         ├── sub_question 추출
          │         ├── coverage 평가 (NLI)
          │         └── gap 감지 → 보완 검색 트리거 (optional)
          │
          ├── PromptFactory.build_phase1_prompt()   ← think prompt
          ├── call_ollama(phase=1, no format=json)  ← reasoning
          │
          ├── PromptFactory.build_phase2_prompt()   ← structured output prompt
          ├── call_ollama(phase=2, format=json)     ← JSON 생성
          │
          ├── parse_qa_json_response()               ← 기존 파서 재사용
          │
          ├── FaithfulnessVerifier.verify()          ← claim-evidence 검증
          │
          ├── citation_mapper()                      ← 기존 유지
          └── normalize_response()                   ← 기존 스키마 유지
```

### 7.3 신규 컴포넌트 목록

| 컴포넌트 | 위치 | 역할 |
|---|---|---|
| `SEAModule` | `app/generation/sea/sea_module.py` | 증거 갭 분석 |
| `FaithfulnessVerifier` | `app/generation/validators/faithfulness_verifier.py` | claim-evidence 검증 |
| `TwoPhaseCallStrategy` | `app/generation/llm/two_phase_strategy.py` | Phase 1/2 Ollama 호출 조율 |
| Phase 1 Prompt Template | `app/generation/prompts/phase1_templates/` | topic별 reasoning 프롬프트 |
| Phase 2 Prompt Template | `app/generation/prompts/phase2_templates/` | topic별 structured output 프롬프트 |

---

## 8. 인터페이스 명세

### 8.1 GenerationService 인터페이스 (변경 없음)

```python
# 외부 인터페이스 변경 없음
async def generate(
    self,
    question: str,
    context: List[Dict[str, Any]],
    routing_trace: Optional[dict] = None,
) -> dict:  # normalize_response() 출력 스키마 유지
    ...
```

### 8.2 SEAModule 인터페이스

```python
class SEAModule:
    def __init__(
        self,
        nli_model_name: str = "snunlp/KR-FinBert-SC",
        coverage_threshold: float = 0.6,
    ): ...

    async def assess(
        self,
        sub_questions: List[str],
        passages: List[str],
    ) -> SEAResult: ...
```

### 8.3 TwoPhaseCallStrategy 인터페이스

```python
class TwoPhaseCallStrategy:
    async def call(
        self,
        phase1_prompt: str,
        phase2_prompt_template: str,
        topic_type: str,
        complexity_level: str,
    ) -> TwoPhaseResult: ...

@dataclass
class TwoPhaseResult:
    phase1_think: str
    phase2_json_raw: str
    phase1_latency_ms: float
    phase2_latency_ms: float
    phase1_token_count: int
    phase2_token_count: int
    retry_count: int
```

### 8.4 FaithfulnessVerifier 인터페이스

```python
class FaithfulnessVerifier:
    async def verify(
        self,
        answer: str,
        passages: List[str],
    ) -> FaithfulnessResult: ...

@dataclass
class FaithfulnessResult:
    faithful_ratio: float
    unsupported_claims: List[str]
    latency_ms: float
```

### 8.5 Ollama 호출 파라미터 변경

| 파라미터 | 현재값 | Phase 1 | Phase 2 |
|---|---|---|---|
| `format` | `"json"` | **미설정** | `"json"` |
| `temperature` | 0.7 | 0.7 | **0.1** |
| `num_predict` | 128 | **512** | **1024** |
| `num_ctx` | 1024 | **4096** | **4096** |

---

## 9. 예외 처리 및 엣지 케이스

### 9.1 2단계 생성 예외

| 예외 상황 | 감지 방법 | 대응 |
|---|---|---|
| Phase 1 `<think>` 태그 없음 | regex 확인 | Phase 1 원본 텍스트를 reasoning으로 사용 후 Phase 2 진행 |
| Phase 1 타임아웃 | httpx.ReadTimeout | Phase 1 생략, Phase 2 단독 실행 (경고 로그) |
| Phase 2 JSON 파싱 실패 1회 | json.JSONDecodeError | Phase 2 재시도 (temperature 0.05로 낮춤) |
| Phase 2 JSON 파싱 실패 2회 | json.JSONDecodeError | `GenerationError(PROCESSING_ERROR)` 반환 |
| `num_predict` 초과로 인한 truncation | `finish_reason == "length"` 확인 | `num_predict`를 50% 증가 후 Phase 2 재시도 (1회) |

### 9.2 SEA 모듈 예외

| 예외 상황 | 감지 방법 | 대응 |
|---|---|---|
| NLI 모델 로드 실패 | 첫 호출 시 예외 | SEA 건너뛰기, `sea_result.error: "model_load_failed"` 기록 |
| sub_questions 빈 목록 | `len(sub_questions) == 0` | SEA 건너뛰기 |
| 보완 검색 결과 없음 | `len(supplementary_docs) == 0` | 보완 없이 Generation 진행, `limitations`에 추가 |
| SEA 타임아웃 (>300ms) | asyncio.wait_for | SEA 결과 없이 Generation 진행 |

### 9.3 Faithfulness 검증 예외

| 예외 상황 | 감지 방법 | 대응 |
|---|---|---|
| NLI 모델 오류 | 예외 캐치 | `faithful_ratio: null`, `hallucination_flag`는 기존 citation 기반으로 유지 |
| claim 추출 실패 | 빈 리스트 반환 | 검증 생략, `faithful_ratio: null` |
| answer 텍스트 없음 | `len(answer) == 0` | 검증 생략 |

### 9.4 엣지 케이스

| 케이스 | 처리 방법 |
|---|---|
| context(검색 결과)가 빈 목록 | Phase 1에 "검색 결과 없음" 안내 포함, `limitations`에 "근거 문서 없음" 추가 |
| 질문이 한글이 아닌 경우 | topic_type="general"로 처리, 다국어 프롬프트 template 적용 |
| DCI trajectory가 포함된 context | evidence_chain에 `[DCI Step N]` prefix를 추가하여 Phase 1에서 출처 구분 가능하게 함 |
| Phase 1 reasoning이 1,000자 초과 | Phase 2 prompt에 reasoning 앞 500자 + 뒤 500자만 포함 (중간 생략 표시) |
| `[[출처 N]]`에서 N이 context 범위 초과 | citation_mapper에서 invalid citation으로 필터링 (기존 동작 유지) |
| 동일 질의 반복 호출 (캐시 대상) | Phase 1 reasoning은 캐시 미적용, Phase 2 결과는 5분 TTL 캐시 고려 (v1.1) |

---

## 10. 마이그레이션 계획

### 10.1 하위 호환성 보장

`normalize_response()` 출력 스키마의 6개 최상위 키(`routing_trace`, `structured_output`, `answer`, `citations`, `limitations`, `latency_ms`, `quality_signals`)는 고도화 후에도 동일하게 유지된다. `quality_signals`에 신규 필드가 추가되지만 기존 필드는 제거하지 않는다. FR-4 API를 소비하는 프론트엔드, 외부 시스템의 코드 변경은 불필요하다.

### 10.2 단계별 마이그레이션

**Phase 0: 기준선 측정 (0주차)**
- 현재 JSON 파싱 실패율, hallucination 발생률, citation coverage를 eval_set_v1 기준으로 재측정하여 문서화
- NLI 모델(`snunlp/KR-FinBert-SC`) 성능 사전 검증: 한국어 민원 텍스트 기준 정밀도/재현율 측정

**Phase 1: num_predict/num_ctx 개선 (1주차)**
- `num_predict: 128 → 512`, `num_ctx: 1024 → 4096`으로 즉시 변경
- Truncation 비율 0% 달성 검증
- 지연 변화 측정: P95 변동폭 ≤ 200ms 목표

**Phase 2: 2단계 생성 분리 (2-3주차)**
- `TwoPhaseCallStrategy` 구현 및 unit test
- Feature flag `GENERATION_TWO_PHASE=false`로 기본 비활성화
- staging 환경에서 eval_set_v1 전체 실행 → JSON 파싱 성공률 ≥ 98% 확인 후 production 전환
- `GENERATION_TWO_PHASE=true`로 전환

**Phase 3: SEA 모듈 (4-5주차)**
- `SEAModule` 구현 및 NLI 모델 통합
- Feature flag `SEA_ENABLED=false`로 기본 비활성화
- complexity=high 질의 10% Shadow mode: SEA 실행하되 결과는 로깅만
- 갭 탐지율 ≥ 85% 확인 후 `SEA_ENABLED=true` 전환

**Phase 4: Faithfulness 검증 (6주차)**
- `FaithfulnessVerifier` 구현
- `FAITHFULNESS_ENABLED=false`로 기본 비활성화
- hallucination 평가 데이터셋 구축 (100건, 수동 레이블링)
- 정밀도 ≥ 85% 확인 후 `FAITHFULNESS_ENABLED=true` 전환

**Phase 5: 안정화 (7-8주차)**
- 전체 기능 활성화 상태에서 2주간 운영 모니터링
- KPI 달성 여부 최종 검증
- 불필요한 레거시 코드 정리 (단일 phase 호출 경로)

### 10.3 롤백 계획

| 롤백 트리거 | 자동 롤백 | 수동 롤백 |
|---|---|---|
| JSON 파싱 실패율 > 5% (5분 이내) | Feature flag `GENERATION_TWO_PHASE=false` 자동 전환 | 동일 |
| Generation P95 > 4,000ms (10분 지속) | 동일 | 동일 |
| Ollama OOM (GPU 메모리 초과) | num_ctx를 2048로 자동 감소 | `num_ctx` 설정 수동 조정 |
| hallucination_flag_rate 급증 > 25% | 경고 알림만, 자동 롤백 없음 | 수동 분석 후 결정 |

---

## 11. 의존성 및 리스크

### 11.1 외부 의존성

| 의존성 | 버전 | 용도 | 대안 |
|---|---|---|---|
| Ollama | ≥ 0.3.x | Phase 1/2 LLM 실행 | — |
| snunlp/KR-FinBert-SC | — | SEA/Faithfulness NLI | KoELECTRA, bge-reranker (한국어) |
| sentence-transformers | ≥ 2.x | NLI 모델 실행 | transformers 직접 사용 |
| httpx | ≥ 0.27.x | Ollama API 호출 | 기존 버전 유지 |

### 11.2 리스크 및 완화 방안

| 리스크 | 발생 확률 | 영향도 | 완화 방안 |
|---|---|---|---|
| Phase 1+2 지연 합산으로 SLA 초과 | 중 | 고 | Phase 1 thinking을 200토큰 이하로 제한하는 max_think_tokens 파라미터 도입 |
| NLI 모델의 한국어 민원 도메인 적합성 부족 | 중 | 중 | Phase 0에서 도메인 검증 후 모델 교체 가능하도록 `NLI_MODEL_NAME` 환경 변수로 분리 |
| GPU 메모리 부족 (num_ctx 4096 증가) | 중 | 고 | num_ctx를 설정으로 분리, OOM 시 자동 감소 로직 추가 |
| SEA 보완 검색이 총 지연을 크게 증가시킴 | 중 | 중 | 보완 검색은 Hybrid 경로만 사용 (DCI 재실행 불가), 보완 검색 TTL 캐시 도입 |
| Phase 2에서 Phase 1 reasoning을 잘못 활용 | 저 | 중 | Phase 2 프롬프트에 reasoning 활용 지침 명시, 10개 golden sample로 few-shot 검증 |

---

## 12. 출시 범위 및 단계 계획 (Phasing)

### MVP (Phase 1-2, 3주)

- [ ] `num_predict: 512`, `num_ctx: 4096` 즉시 적용
- [ ] `TwoPhaseCallStrategy` 구현 (`call_ollama` 2회 호출)
- [ ] Phase 1/2 프롬프트 템플릿 분리 (topic별 4종 × 2 phase)
- [ ] `generation_trace` 확장 (phase1_think, phase1_latency_ms, phase2_latency_ms)
- [ ] Feature flag `GENERATION_TWO_PHASE` 구현
- [ ] Unit test: TwoPhaseCallStrategy, PromptFactory (phase1/2)
- [ ] JSON 파싱 성공률 ≥ 98% 검증

### v1.0 (Phase 3-4, 6주)

- [ ] `SEAModule` 구현 (NLI 통합, coverage 평가, 보완 검색 트리거)
- [ ] `FaithfulnessVerifier` 구현
- [ ] `quality_signals` 확장 (faithful_ratio, unsupported_claims, sea_coverage)
- [ ] Feature flag `SEA_ENABLED`, `FAITHFULNESS_ENABLED` 구현
- [ ] Prometheus 메트릭 추가
- [ ] Hallucination 평가 데이터셋 구축 및 정밀도 검증

### v1.1 (Phase 5 이후)

- [ ] Phase 1 결과 캐시 (동일 질의 + 동일 context 해시 기준 5분 TTL)
- [ ] RAFT/CRAFT 방식의 민원 도메인 LoRA 어댑터 학습 검토
- [ ] CTRL-RAG 방식의 Contrastive Likelihood Reward RL 적용 검토
- [ ] 멀티턴 대화 컨텍스트 지원 (이전 턴 reasoning 활용)

---

*본 PRD는 초안이며, 검토 후 확정 버전으로 업데이트됩니다.*  
*변경 이력은 Git commit history로 관리합니다.*
