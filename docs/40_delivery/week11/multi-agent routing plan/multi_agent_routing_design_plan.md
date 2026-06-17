# 복합 민원 분할 협업 에이전트 설계 계획

## 1. 문서 목적

이 문서는 현재 AI-Civil-Affairs-Systems에 복합 민원 분할 협업 에이전트
기능을 추가하기 위한 설계 계획을 정리한다.

목표는 기존 Adaptive RAG, 담당부서 추정, 법령 grounding, 회신 생성,
LLM-Rubric 평가 체계를 재사용하면서, 하나의 복합 민원을 여러 하위 이슈와
담당 부서 단위로 분해하고 최종 통합 회신까지 생성하는 것이다.

본 문서는 구현 상세 코드 명세가 아니라 팀원들이 같은 방향으로 이해하고
후속 이슈를 나눌 수 있도록 하는 상위 설계 문서다.

참고 논문:

| 구분 | 논문 제목 | 링크 |
| --- | --- | --- |
| 메인 구조 | HuggingGPT: Solving AI Tasks with ChatGPT and its Friends in Hugging Face | <https://arxiv.org/abs/2303.17580> |
| 역할 기반 협업 | MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework | <https://arxiv.org/abs/2308.00352> |
| 추론-행동 Trace | ReAct: Synergizing Reasoning and Acting in Language Models | <https://arxiv.org/abs/2210.03629> |
| 구현 참고 | AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation | <https://arxiv.org/abs/2308.08155> |
| 분해 프롬프트 | Least-to-Most Prompting Enables Complex Reasoning in Large Language Models | <https://arxiv.org/abs/2205.10625> |

본 설계에서는 HuggingGPT를 전체 파이프라인의 기본 구조로 삼고,
MetaGPT는 부서별 역할 에이전트 설계 근거로, ReAct는 설명 가능한
`multi_agent_trace` 설계 근거로 사용한다. AutoGen은 프레임워크 도입
대상이 아니라 구현 패턴 참고로만 두며, Least-to-Most Prompting은
복합 민원 분해 프롬프트의 보조 근거로 활용한다.


## 2. 배경

현재 시스템은 단일 민원에 대해 다음 흐름을 갖는다.

```text
민원 입력
  -> Topic/Complexity 분석
  -> Adaptive Retrieval
  -> 법령/근거 grounding
  -> GenerationService 회신 생성
  -> LLM-Rubric 평가
```

이 구조는 단일 쟁점 민원에는 적합하지만, 실제 민원에는 여러 부서가 함께
관여해야 하는 경우가 많다.

예시는 다음과 같다.

```text
도로가 깨져서 교통이 막히고, 그 주변 불법 주차 때문에 위험합니다.
```

이 민원에는 최소 두 개의 쟁점이 섞여 있다.

- 도로 파손 및 보수: 도로과, 건설과 등
- 불법 주정차 및 교통 안전: 주차지원과, 교통행정과 등

기존 단일 RAG 방식은 이러한 복합 민원을 하나의 query로 검색하고 하나의
답변으로 생성하기 때문에 다음 문제가 발생할 수 있다.

- 일부 쟁점만 검색되고 다른 쟁점이 누락된다.
- 담당 부서가 하나로만 좁혀져 협조 부서가 드러나지 않는다.
- 답변에서 도로 보수와 주정차 단속의 책임 경계가 섞인다.
- 근거가 없는 확정 조치나 권한 밖 약속이 생성된다.
- LLM-Rubric Q8 업무 완결성과 Q4 citation 정확성이 낮아진다.

따라서 복합 민원에서는 단일 query 중심 처리보다, 하위 이슈별 분해와
부서별 근거 수집, 최종 조율이 필요하다.

## 3. 참고 논문과 설계 매핑

첨부 검토 대화에서 정리한 논문 조합은 다음과 같이 적용한다.

| 논문/방법 | 프로젝트 적용 | 설계상 역할 |
| --- | --- | --- |
| HuggingGPT | 전체 처리 파이프라인 | 작업 분해, 담당 부서 선택, 하위 작업 실행, 최종 응답 통합 |
| MetaGPT | 역할 기반 에이전트 구조 | Decomposer, Router, Department Agent, Coordinator, Verifier 역할 분리 |
| ReAct | 설명 가능한 라우팅 trace | 분해 이유, 부서 선택 이유, 검색 행동과 근거를 `multi_agent_trace`에 기록 |
| Least-to-Most Prompting | 분해 프롬프트 설계 | 복합 민원을 단순 하위 이슈로 순차 분해 |
| AutoGen | 후순위 구현 참고 | 별도 프레임워크 도입보다 현재 FastAPI 구조 유지가 우선 |

핵심은 새 멀티에이전트 프레임워크를 도입하는 것이 아니라, 기존 시스템 위에
얇은 orchestration layer를 추가하는 것이다.

## 4. 목표

### 4.1 기능 목표

1. 복합 민원을 하위 이슈 단위로 분해한다.
2. 각 하위 이슈에 담당 부서 후보를 매핑한다.
3. 하위 이슈별로 기존 RetrievalService를 실행한다.
4. 하위 이슈별로 부서 관점의 답변 초안을 생성한다.
5. 최종 Coordinator가 중복, 충돌, 책임 경계를 정리한다.
6. 통합 공문서형 회신과 검토 가능한 trace를 함께 반환한다.
7. LLM-Rubric으로 기존 단일 RAG 대비 Q8, citation, semantic risk 개선 여부를 평가한다.

### 4.2 비목표

MVP 단계에서는 다음을 하지 않는다.

- AutoGen 같은 외부 멀티에이전트 프레임워크 도입
- 여러 LLM 모델을 실제로 부서별로 따로 운영
- 사람 승인 없이 최종 답변 자동 발송
- 모든 부서 업무 규칙을 완전한 SOP로 모델링
- 4개 이상의 하위 이슈를 무제한 병렬 처리

## 5. 현재 프로젝트 자산과 연결점

| 기존 자산 | 현재 역할 | 멀티에이전트 적용 방식 |
| --- | --- | --- |
| `ComplexityAnalyzer` | 복잡도와 request segment 산출 | 복합 민원 활성화 조건으로 사용 |
| `routing_trace.request_segments` | 요청 세그먼트 기록 | 초기 issue segment 후보로 사용 |
| `DepartmentAssigner` | 담당 부서 후보 추정 | segment별 부서 라우팅에 재사용 |
| `RetrievalService.search()` | Adaptive RAG 검색 | segment별 검색 실행에 재사용 |
| `PromptFactory` | 생성 프롬프트 구성 | 부서별 draft prompt와 coordinator prompt 추가 |
| `GenerationService` | 회신 생성 | segment draft와 최종 통합 회신 생성에 재사용 |
| `qa_response_validator` | citation 형식 검증 | 통합 답변 검증에 재사용 |
| LLM-Rubric 평가기 | 생성 품질 평가 | multi-agent 전후 비교 평가에 확장 |

## 6. 목표 아키텍처

### 6.1 전체 흐름

```text
[시민 민원 입력]
        |
        v
[MultiComplaintOrchestrator]
        |
        +-- 1. ComplaintDecomposer
        |      복합 민원을 하위 이슈로 분해
        |
        +-- 2. SegmentDepartmentRouter
        |      각 이슈의 담당 부서 후보와 대표 부서 선택
        |
        +-- 3. DepartmentRAGAgent
        |      이슈별 유사 민원, 법령, 처리 사례 검색
        |
        +-- 4. DepartmentDraftAgent
        |      부서별 답변 초안 생성
        |
        +-- 5. CoordinatorAgent
        |      중복 제거, 책임 경계 정리, 통합 회신 생성
        |
        +-- 6. Evidence/Safety Verifier
               citation, 권한 초과, 결론 반전 위험 검토
```

### 6.2 기존 API와의 관계

MVP에서는 외부 API를 크게 바꾸지 않는다.

- `/qa`는 기존 단일 답변을 계속 반환한다.
- 복합 민원으로 판단된 경우 내부적으로 multi-agent routing을 사용한다.
- 기존 `routing_trace`는 유지한다.
- 신규 trace는 `generation_metadata.multi_agent_trace` 또는
  `routing_trace.multi_agent_trace`에 추가한다.

프론트엔드 Workbench에서는 우선 trace JSON을 펼쳐 볼 수 있게 하고,
이후 별도 카드 UI로 확장한다.

## 7. 신규 컴포넌트 설계

### 7.1 MultiComplaintOrchestrator

역할:

- 복합 민원 여부를 판단한다.
- 하위 에이전트 실행 순서를 조율한다.
- 실패 시 기존 단일 RAG 경로로 폴백한다.

활성화 조건:

- `complexity_level == "high"`
- 또는 `request_segments` 길이 2 이상
- 또는 부서 후보가 2개 이상이고 confidence가 유의미한 경우

권장 위치:

```text
app/generation/multi_agent/orchestrator.py
```

### 7.2 ComplaintDecomposer

역할:

- 민원 원문을 하위 이슈로 분해한다.
- 각 이슈에 핵심 요청, 대상 시설, 행정 행위, 위험 표현을 붙인다.

출력 예시:

```json
[
  {
    "segment_id": "S1",
    "issue": "도로 파손으로 인한 통행 불편",
    "intent": "보수 요청",
    "entities": ["도로", "파손", "통행 불편"],
    "risk_terms": ["위험", "교통 지장"]
  },
  {
    "segment_id": "S2",
    "issue": "주변 불법 주정차로 인한 안전 위험",
    "intent": "단속 요청",
    "entities": ["불법 주차", "안전 위험"],
    "risk_terms": ["위험"]
  }
]
```

MVP 구현 방식:

- 1차: 기존 `routing_trace.request_segments`를 정규화하여 사용
- 2차: 규칙 기반 분리 보강
- 3차: LLM 기반 decomposer prompt 추가

### 7.3 SegmentDepartmentRouter

역할:

- 각 segment에 대해 담당 부서 후보를 산출한다.
- 대표 부서와 협조 부서를 구분한다.
- 선택 이유를 trace로 남긴다.

기존 `DepartmentAssigner`를 segment별로 호출한다.

출력 예시:

```json
{
  "segment_id": "S1",
  "department_candidates": [
    {"name": "도로과", "confidence": 0.82, "evidence": ["도로", "보수"]},
    {"name": "건설과", "confidence": 0.61, "evidence": ["공사", "시설물"]}
  ],
  "selected_department": "도로과",
  "coordination_role": "primary",
  "route_reason": "도로 시설물 보수와 통행 안전 조치 소관"
}
```

### 7.4 DepartmentRAGAgent

역할:

- segment별 query를 구성한다.
- 담당 부서 hint와 issue text를 함께 넣어 검색한다.
- 검색 결과에 `segment_id`, `selected_department`, `source_type`을 붙인다.

검색 query 예시:

```text
[도로과] 도로 파손으로 인한 통행 불편 보수 요청
```

MVP에서는 기존 `RetrievalService.search()`를 그대로 사용하고, query signal에
`responsible_units`를 넣는 방식을 우선 검토한다.

### 7.5 DepartmentDraftAgent

역할:

- 각 segment의 검색 근거를 바탕으로 부서별 답변 초안을 만든다.
- 초안은 최종 회신이 아니라 Coordinator 입력으로 사용된다.

초안 출력 예시:

```json
{
  "segment_id": "S1",
  "department": "도로과",
  "draft_answer": "도로 파손 사항은 현장 확인 후 보수 필요 여부를 검토하겠습니다...",
  "citations": ["DOC-001", "DOC-018"],
  "limitations": ["정확한 위치 확인 필요"]
}
```

프롬프트 원칙:

- 해당 부서 소관 범위 안에서만 답변한다.
- 타 부서 사안은 직접 처리 약속을 하지 않는다.
- 근거 없는 완료, 예정, 확정 조치를 쓰지 않는다.
- citation이 없는 주장은 제한한다.

### 7.6 CoordinatorAgent

역할:

- 부서별 초안을 하나의 공문서형 회신으로 통합한다.
- 중복 문장을 제거한다.
- 부서 간 책임 경계를 명확히 한다.
- 협조 부서와 주관 부서를 구분한다.
- 상충되는 답변이 있으면 확정하지 않고 검토 필요로 표시한다.

통합 답변 구조 예시:

```text
귀하께서 제기하신 민원은 도로 파손에 따른 통행 불편과 불법 주정차로 인한
안전 우려가 함께 포함된 사안으로 확인됩니다.

도로 파손 부분은 도로과 소관으로, 현장 위치와 파손 범위 확인 후 보수 필요
여부를 검토할 수 있습니다. [[출처 1]]

불법 주정차 부분은 주차지원과 소관으로, 단속 가능 구역 여부와 현장 상황을
확인한 뒤 관련 절차에 따라 조치 여부를 검토할 수 있습니다. [[출처 2]]

다만 정확한 조치 가능 여부는 현장 확인과 관련 부서 검토 결과에 따라 달라질
수 있습니다.
```

### 7.7 Evidence/Safety Verifier

역할:

- 최종 답변의 citation 누락을 확인한다.
- `unsupported_commitment`, `authority_mismatch`, `disposition_reversal` 위험을 확인한다.
- 누락 segment가 있는지 확인한다.

MVP에서는 기존 LLM-Rubric semantic risk와 generation validator 규칙을
사후 평가에 우선 사용한다. 운영 경로에서는 경고 trace만 남기고 자동 차단은
후속 단계에서 검토한다.

## 8. 데이터 스키마 초안

### 8.1 MultiAgentTrace

```json
{
  "enabled": true,
  "activation_reason": "complexity_high_and_multiple_segments",
  "segment_count": 2,
  "segments": [
    {
      "segment_id": "S1",
      "issue": "도로 파손으로 인한 통행 불편",
      "intent": "보수 요청",
      "selected_department": "도로과",
      "department_candidates": [
        {
          "name": "도로과",
          "confidence": 0.82,
          "evidence": ["도로", "파손", "보수"]
        }
      ],
      "route_reason": "도로 시설물 보수 소관",
      "retrieval": {
        "query": "[도로과] 도로 파손으로 인한 통행 불편 보수 요청",
        "retrieved_doc_count": 4,
        "doc_ids": ["CASE-001__chunk-0"]
      },
      "draft": {
        "status": "generated",
        "citation_count": 2,
        "limitations": ["정확한 위치 확인 필요"]
      }
    }
  ],
  "coordination": {
    "merge_policy": "primary_department_order",
    "conflicts": [],
    "missing_evidence_segments": [],
    "final_answer_status": "generated"
  },
  "latency_ms": {
    "decompose": 35.2,
    "department_route": 86.1,
    "segment_retrieval": 340.5,
    "segment_generation": 2200.0,
    "coordination": 780.4,
    "total": 3442.2
  }
}
```

### 8.2 Segment 객체

```python
class IssueSegment:
    segment_id: str
    issue: str
    intent: str
    entities: list[str]
    risk_terms: list[str]
    selected_department: str | None
    department_candidates: list[dict]
    retrieval_query: str
    retrieved_doc_ids: list[str]
    draft_answer: str
    citations: list[dict]
    limitations: list[str]
```

## 9. 프롬프트 설계 초안

### 9.1 Decomposer Prompt

```text
당신은 지방자치단체 민원 접수 내용을 하위 이슈로 분해하는 분석기입니다.

규칙:
1. 하나의 민원 안에 서로 다른 조치 대상, 담당 부서, 행정 행위가 있으면 분리합니다.
2. 같은 부서에서 처리할 수 있는 중복 표현은 하나의 이슈로 합칩니다.
3. 최대 3개 이슈까지만 생성합니다.
4. 각 이슈에는 issue, intent, entities, risk_terms를 포함합니다.
5. 추측으로 조치 가능 여부를 판단하지 않습니다.
```

### 9.2 Department Draft Prompt

```text
당신은 {department} 소관 민원 답변 초안을 작성하는 행정 AI입니다.

입력:
- 전체 민원: {original_question}
- 담당 이슈: {segment_issue}
- 검색 근거: {segment_evidence}

작성 규칙:
1. {department} 소관 범위의 이슈만 답변합니다.
2. 타 부서 소관은 직접 처리 약속을 하지 말고 협조 또는 이첩 필요로 표현합니다.
3. 근거 문서에 없는 설치, 철거, 단속 완료, 예산 확보, 일정 확정을 쓰지 않습니다.
4. 필요한 경우 현장 확인, 관계 부서 검토, 추가 정보 필요를 명시합니다.
5. 근거가 있는 문장에는 [[출처 N]]을 붙입니다.
```

### 9.3 Coordinator Prompt

```text
당신은 여러 부서의 민원 답변 초안을 하나의 통합 회신으로 조율하는 담당자입니다.

입력:
- 원 민원
- 하위 이슈 목록
- 부서별 초안
- 부서별 citation
- limitations

통합 규칙:
1. 모든 하위 이슈를 빠짐없이 다룹니다.
2. 중복된 인사말과 반복 문장은 제거합니다.
3. 주관 부서와 협조 부서를 구분합니다.
4. 서로 충돌하는 초안은 확정하지 말고 검토 필요로 표시합니다.
5. 근거 없는 확정 조치를 약속하지 않습니다.
6. 최종 답변은 공공기관 회신 문체로 작성합니다.
```

## 10. MVP 범위

MVP는 구현 부담을 줄이기 위해 다음 범위로 제한한다.

| 항목 | MVP 결정 |
| --- | --- |
| 활성화 대상 | `complexity=high` 또는 request segment 2개 이상 |
| 최대 segment 수 | 3개 |
| 부서 후보 | segment별 top-3 |
| 부서별 LLM | 동일 모델, prompt role만 변경 |
| 검색 | 기존 `RetrievalService.search()` 재사용 |
| 생성 | 기존 `GenerationService` 재사용 |
| 최종 병합 | Coordinator prompt 1회 호출 |
| 검증 | 기존 citation validator + LLM-Rubric 사후 평가 |
| UI | 우선 JSON trace 표시, 카드 UI는 후속 |

## 11. 단계별 구현 계획

### Phase 0: 설계 고정과 평가셋 준비

- 복합 민원 예시 30~50건을 수집한다.
- 각 민원에 gold segment와 gold responsible department를 수동 라벨링한다.
- 현재 단일 RAG 경로의 Q0, Q4, Q8, semantic risk baseline을 측정한다.
- `multi_agent_trace` 스키마를 확정한다.

완료 기준:

- 복합 민원 평가셋 v0 생성
- 단일 RAG baseline 리포트 작성
- API 응답 확장 위치 합의

### Phase 1: Decomposer + Department Router

- `ComplaintDecomposer`를 구현한다.
- 기존 `request_segments`를 우선 사용하고, 부족하면 규칙 기반 보강을 적용한다.
- segment별 `DepartmentAssigner` 호출을 연결한다.
- `multi_agent_trace.segments[].department_candidates`를 생성한다.

완료 기준:

- segment coverage 0.80 이상
- 담당부서 Recall@3 0.70 이상
- 기존 단일 `/qa` 동작 회귀 없음

### Phase 2: Segment별 Retrieval

- segment별 retrieval query를 구성한다.
- `responsible_units` query signal 주입을 검토한다.
- 검색 결과에 segment metadata를 붙인다.
- segment별 retrieved doc count와 doc id를 trace에 기록한다.

완료 기준:

- 각 segment별 citation 후보 1개 이상 확보 비율 0.80 이상
- 검색 실패 segment가 trace에 명확히 기록됨

### Phase 3: Department Draft + Coordinator

- 부서별 draft prompt를 추가한다.
- segment별 초안을 생성한다.
- Coordinator prompt로 통합 답변을 생성한다.
- 중복 문장과 부서 책임 경계를 정리한다.

완료 기준:

- 모든 segment가 최종 답변에 반영되는 비율 0.80 이상
- Q8 업무 완결성 기존 대비 +1.0점 이상 개선 목표
- empty answer 0건

### Phase 4: Safety/Evidence 검증과 평가

- 최종 답변에 대해 citation coverage를 계산한다.
- `unsupported_commitment`, `authority_mismatch`, `disposition_reversal`를 평가한다.
- LLM-Rubric에 segment coverage와 department coverage 보조 지표를 추가한다.
- 단일 RAG 대비 multi-agent 경로의 결과를 비교한다.

완료 기준:

- Q4 citation 정확성 개선
- semantic risk 건수 감소
- 검토 보고서 작성

## 12. 평가 계획

### 12.1 비교 대상

| Baseline | 설명 |
| --- | --- |
| Single RAG | 현재 `/qa` 기본 경로 |
| Single RAG + responsible_unit hint | 단일 답변이지만 부서 신호만 강화 |
| Multi-Agent Routing MVP | segment 분해, 부서별 검색, 통합 답변 |

### 12.2 정량 지표

| 지표 | 의미 | 목표 |
| --- | --- | ---: |
| Segment Coverage | gold 하위 이슈 중 시스템이 포착한 비율 | 0.80 이상 |
| Department Recall@3 | segment별 정답 부서가 top-3에 포함된 비율 | 0.70 이상 |
| Segment Evidence Coverage | 각 segment에 검색 근거가 붙은 비율 | 0.80 이상 |
| Final Answer Segment Coverage | 최종 답변에 각 segment가 반영된 비율 | 0.80 이상 |
| Citation Coverage | 답변 주요 주장에 citation이 붙은 비율 | 0.80 이상 |
| LLM-Rubric Q8 | 업무 완결성 | 기존 대비 +1.0 |
| Semantic Risk Count | 결론 반전, 권한 초과, 근거 없는 약속 | 기존 대비 감소 |
| Latency P95 | 전체 응답 시간 | MVP에서는 baseline 대비 2배 이내 |

### 12.3 정성 평가

사람 검토자는 다음 질문에 답한다.

1. 모든 주요 민원 쟁점이 빠짐없이 다뤄졌는가?
2. 각 쟁점의 담당 부서가 적절한가?
3. 주관 부서와 협조 부서의 책임 경계가 명확한가?
4. 근거 없는 확정 약속이 없는가?
5. 최종 회신이 하나의 공문서처럼 자연스럽게 읽히는가?

## 13. API와 UI 영향

### 13.1 API 영향

기존 필드는 유지한다.

- `routing_trace`
- `structured_output`
- `answer`
- `citations`
- `limitations`
- `quality_signals`
- `generation_metadata`

추가 후보:

```json
{
  "generation_metadata": {
    "multi_agent_trace": {...}
  },
  "quality_signals": {
    "segment_coverage": 0.85,
    "department_coverage": 0.75,
    "coordination_conflict_count": 0
  }
}
```

기존 클라이언트가 깨지지 않도록 top-level 필드 추가는 피하고,
기존 metadata 내부 확장을 우선한다.

### 13.2 UI 영향

MVP UI는 다음 정보만 표시해도 충분하다.

- 복합 민원 여부
- 하위 이슈 목록
- 이슈별 담당 부서 후보
- 이슈별 검색 근거 수
- 최종 통합 답변
- 누락 이슈 또는 검토 필요 경고

후속으로는 `SegmentTraceCard`, `DepartmentDraftCard`, `CoordinationSummaryCard`
같은 Workbench 카드를 추가할 수 있다.

## 14. 리스크와 완화 방안

| 리스크 | 영향 | 완화 |
| --- | --- | --- |
| segment 분해 오류 | 잘못된 부서 라우팅과 누락 답변 발생 | 최대 3개 제한, 사람 검토 trace 제공 |
| 담당부서 후보 부정확 | 답변 책임 경계 오류 | top-1 확정 대신 top-3 후보와 confidence 표시 |
| segment별 LLM 호출로 지연 증가 | 응답 시간 증가 | MVP는 complexity=high에만 적용, segment 병렬 실행 검토 |
| 부서별 초안 간 충돌 | 최종 답변 일관성 저하 | Coordinator가 conflict를 확정하지 않고 검토 필요로 표시 |
| citation 병합 오류 | Q4 저하 | citation id 재매핑 단계 추가 |
| 권한 밖 약속 생성 | 행정 안전성 저하 | safety verifier와 LLM-Rubric semantic risk 적용 |

## 15. 팀 작업 분해 초안

| 역할 | 작업 |
| --- | --- |
| BE1/Structuring | Decomposer, segment schema, DepartmentAssigner segment 호출 |
| BE2/Retrieval | segment별 검색 query, responsible unit signal, retrieval trace 확장 |
| BE3/Generation | Department draft prompt, Coordinator prompt, citation 재매핑 |
| Evaluation | 복합 민원 평가셋, segment coverage, LLM-Rubric 확장 |
| FE/Workbench | multi-agent trace 표시 UI |

## 16. 권장 파일 구조

```text
app/
  generation/
    multi_agent/
      __init__.py
      orchestrator.py
      schemas.py
      decomposer.py
      department_router.py
      coordinator.py
      verifier.py
    prompts/
      multi_agent_templates.py

scripts/
  evaluate_multi_agent_routing.py

docs/
  40_delivery/
    week11/
      multi_agent_routing_design_plan.md
```

## 17. 발표/보고서용 요약 문장

본 프로젝트의 복합 민원 분할 협업 에이전트는 HuggingGPT의 작업 분해 및
실행 파이프라인을 기본 구조로 삼고, MetaGPT의 역할 기반 협업 방식을
부서별 에이전트 설계에 적용한다. 또한 ReAct의 reasoning-action 개념을
사용자에게 노출 가능한 `multi_agent_trace`로 변환하여, 민원 분할, 부서
라우팅, 근거 검색 과정이 검토 가능한 형태로 남도록 한다.

이를 통해 기존 단일 RAG 방식의 한계였던 복합 민원 쟁점 누락, 담당 부서
혼동, 근거 없는 확정 조치 문제를 줄이고, 여러 부서가 관여하는 민원을
구조적으로 분할, 처리, 취합할 수 있는 행정 AI 시스템으로 고도화한다.

## 18. 최종 판단

현재 프로젝트 상태에서는 복합 민원 협업 기능을 완전히 새로운 프레임워크로
구현하기보다, 기존 Adaptive RAG와 GenerationService 위에 orchestration
계층을 추가하는 방식이 가장 현실적이다.

우선순위는 다음과 같다.

1. `multi_agent_trace` 스키마와 평가셋을 먼저 고정한다.
2. Decomposer와 segment별 Department Router를 구현한다.
3. segment별 Retrieval과 Department Draft를 연결한다.
4. Coordinator로 통합 답변을 생성한다.
5. LLM-Rubric과 사람 검토로 기존 단일 RAG 대비 개선 여부를 검증한다.

이 순서로 진행하면 기존 코드와 평가 자산을 유지하면서도, 발표와 실제
행정 업무 관점에서 설득력 있는 고도화 기능을 만들 수 있다.
