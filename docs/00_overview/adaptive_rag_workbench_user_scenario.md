# Adaptive RAG Workbench 사용자 시나리오 설계서

문서 버전: v1.1  
작성일: 2026-04-09  
기준 문서: PRD v2.1, MVP Scope v2.1

## 1. 문서 목적

본 문서는 "사내 민원 데이터를 분석해 답변을 생성하는 RAG 시스템"에 대해, 민원 담당 공무원이 답변 초안을 확인·수정·확정하는 실제 업무 흐름을 사용자 중심으로 정의한다.  
기술 파이프라인(Analyzer -> Router -> Retrieval -> Generation -> UI)과 사용자 인터랙션을 하나의 시나리오로 연결해, 데모와 운영 전환 모두에 활용 가능한 실행 기준을 제공한다.

## 2. 사용자 페르소나

### 2.1 1차 페르소나: 민원 담당 공무원 (주 사용자)
- 목표: 민원 처리 시간을 줄이면서도 근거 기반 답변의 정확성과 설명 가능성을 확보한다.
- 숙련도: 행정 업무 숙련도 높음, AI 시스템 사용 경험은 중간 수준.
- 주요 니즈:
  - 민원 핵심 요약을 빠르게 파악
  - 유사 민원/규정 근거를 즉시 확인
  - 초안을 직접 수정해 최종 책임을 유지
- 주요 불안 요인:
  - AI 환각으로 인한 부정확 답변
  - 근거 출처가 불명확한 문장
  - 복합 민원에서 일부 요구 누락

### 2.2 2차 페르소나: 팀 관리자 (감독 사용자)
- 목표: 처리 품질과 처리량을 동시에 관리하고, 시연/운영 상태를 점검한다.
- 주요 니즈:
  - 처리 단계별 상태 확인(대기/진행/검토완료)
  - 라우팅 근거와 실패 사례 모니터링
  - KPI(처리 시간, 수정률, 재민원율) 추적

## 3. 컨텍스트 정의 (Context-First)

- 업무 상황: 담당자는 하루 다수 민원을 처리하며, 각 건마다 법규·유사사례 확인에 시간이 소요된다.
- 제약 조건:
  - 로컬/온디바이스 우선 처리
  - 단일 민원뿐 아니라 복합 요청(다중 요구) 처리 필요
  - 최종 답변 책임은 공무원에게 있음 (AI는 보조)
- 시스템 가치 가설:
  - AI가 "요약 + 근거 + 초안"을 동시에 제공하면 검토 시간이 단축된다.
  - 라우팅 트레이스와 citation이 투명하게 노출되면 사용자 신뢰가 상승한다.

## 4. 메인 시나리오 (Happy Path)

### 시나리오 제목
민원 1건 선택 후, Adaptive RAG로 생성된 초안을 검토·수정·확정한다.

### 사전 조건
- 민원 데이터가 수집/정제되어 검색 인덱스에 반영되어 있다.
- Workbench(좌/중/우 3단 UI)와 API(`/search`, `/qa`)가 연결되어 있다.

### 단계별 사용자/시스템 흐름

1. 민원 선택
- 사용자 행동: 중앙 패널에서 처리 대상 민원 1건 선택
- 시스템 반응: 선택 이벤트와 민원 본문을 세션 컨텍스트에 적재
- 사용자 가치: 어떤 건을 처리 중인지 명확히 인지

2. 입력 분석
- 시스템 처리: TopicAnalyzer, ComplexityAnalyzer, MultiRequestDetector(보조) 실행
- 생성 데이터:
  - `topic_type`
  - `complexity_level`
  - `complexity_score`
  - `complexity_trace`
  - `request_segments`
- 사용자 노출: 우측 패널에 "분석 완료" 배지 및 핵심 분류값 표시

3. 전략 라우팅
- 시스템 처리: AdaptiveRouter가 route key `(topic_type, complexity_level)`로 전략 선택
- 생성 데이터:
  - `strategy_id`
  - `route_key`
  - `routing_trace`
- 사용자 노출: "왜 이 전략이 선택되었는지" 요약 문장 표시

4. 근거 검색
- 시스템 처리: Topic/Complexity adaptive retrieval 수행
- 생성 데이터:
  - 유사 민원 후보 목록
  - 각 문서의 score, source, metadata(`strategy_id`, `topic_type`)
- 사용자 노출: 우측 패널 "유사 민원" 및 "근거 목록(citation)" 렌더링

5. 답변 초안 생성
- 시스템 처리: Topic-aware PromptFactory로 프롬프트 구성 후 생성 실행
- 후처리: `normalize_response()`로 통합 스키마 반환
- 생성 데이터:
  - `answer`
  - `citations`
  - `limitations`
  - `structured_output`
  - `routing_trace`
- 사용자 노출: 우측 패널 "답변 초안" + "주의사항/한계" 표시

6. 공무원 검토/수정
- 사용자 행동: 초안 문장을 수정하고 근거 링크를 대조
- 시스템 반응: 수정 이력(diff), 편집 시간, 최종 저장 상태 기록
- 사용자 가치: AI 속도 + 인간 책임성 결합

7. 확정 및 완료
- 사용자 행동: 검토 완료 상태로 전환
- 시스템 반응: 처리 상태를 `검토완료`로 변경, 로그 저장
- 결과: 하나의 연속 흐름에서 민원 처리 완료

## 5. 대안/예외 시나리오 (Edge Cases)

### EC-1: 환각 의심 응답
- 징후: 초안 문장에 citation이 없거나, citation 내용과 문장이 불일치
- 시스템 대응:
  - 신뢰도 경고 배지 노출
  - "근거 부족 문장" 하이라이트
  - 재생성 버튼 제공(근거 우선 모드)
- 사용자 행동: 문제 문장 삭제/수정 후 재생성 요청
- 안전장치: citation 없는 문장은 기본적으로 확정 전 경고

### EC-2: 다중 의도 민원 일부 누락
- 징후: `request_segments`가 2개 이상인데 답변이 특정 세그먼트를 다루지 않음
- 시스템 대응:
  - `request_segments` 체크리스트와 답변 매핑 표시
  - 누락 세그먼트 자동 경고
- 사용자 행동: 누락 항목 보완 요청 또는 수동 추가
- 안전장치: 모든 세그먼트 매핑 전에는 완료 버튼 비활성(옵션)

### EC-3: 검색 품질 저하 (낮은 관련도)
- 징후: 상위 검색 결과 score가 임계치 미만
- 시스템 대응:
  - 검색 범위 확장 전략으로 fallback 라우팅
  - "유사 근거 부족" 안내 및 수동 검색 보조 UI 제공
- 사용자 행동: 키워드 보정 또는 직접 근거 선택

### EC-4: 편향 가능성 표현
- 징후: 특정 집단에 불리하게 해석될 소지가 있는 문장
- 시스템 대응:
  - 금칙/주의 표현 룰 기반 경고
  - 대체 표현 템플릿 제안
- 사용자 행동: 중립적 표현으로 수정

### EC-5: 시스템 지연/실패
- 징후: API 타임아웃 또는 모델 응답 지연
- 시스템 대응:
  - 단계별 진행 상태 표시(Analyzer/Router/Retrieval/Generation)
  - 부분 결과 우선 표시(예: 검색 근거 먼저)
  - 재시도 및 수동 모드 전환
- 사용자 행동: 수동 작성으로 임시 처리 후 재시도

## 6. 시스템 인터랙션 포인트 (단계별 I/O)

| 단계 | 사용자 액션 | 시스템 입력(Input) | 시스템 출력(Output) | 저장/로그 데이터 |
| --- | --- | --- | --- | --- |
| 민원 선택 | 목록에서 민원 클릭 | complaint_id, complaint_text | 선택 상태, 세션 컨텍스트 | selection_timestamp, operator_id |
| Analyzer | 분석 시작(자동) | complaint_text | topic_type, complexity_level, complexity_score, complexity_trace, request_segments | analyzer_latency, analyzer_version |
| Router | 전략 결정(자동) | 분석 메타데이터 | strategy_id, route_key, routing_trace | router_latency, route_decision_log |
| Retrieval | 근거 조회(자동) | route_key, complaint_text | retrieved_docs, scores, citation candidates | retrieval_latency, top_k, filter_params |
| Generation | 초안 생성(자동) | retrieved_docs, prompt template, routing_hint | answer, citations, limitations, structured_output | generation_latency, model_id, token_usage |
| 검토/수정 | 초안 편집 | draft_answer, user_edits | revised_answer, edit_diff | edit_count, edit_time, final_version |
| 완료 처리 | 검토완료 클릭 | final_answer, confirmation_flag | status=검토완료 | completion_timestamp, audit_log |

## 7. 신뢰(Trust) 설계 포인트

- 설명 가능성: `routing_trace`를 "선택 이유" 형태로 자연어 요약해 노출한다.
- 검증 가능성: 각 핵심 주장 문장 옆에 citation 연결을 제공한다.
- 통제 가능성: 공무원이 언제든 초안을 수정/삭제하고 수동 작성으로 전환할 수 있다.
- 경고 일관성: 환각/누락/편향 경고 규칙을 고정해 사용자 학습 부담을 낮춘다.

## 8. 피드백 플라이휠 (Iterative Loop)

1. 운영 중 데이터 수집
- 사용자 수정 diff
- 재생성 발생 사유
- 경고 발생 유형(환각/누락/편향)

2. 주간 분석
- 주제별 수정률
- 전략별 성공률(최종 확정까지 도달 비율)
- citation 불일치 빈도

3. 개선 반영
- Analyzer 분류 규칙 보정
- Router 전략 매핑 조정
- PromptFactory 템플릿 개선

4. 재배포/검증
- 고정된 E2E 시나리오(단일/복합/예외) 회귀 검증
- 성능 및 신뢰 지표 비교

## 9. KPI 연결 (비즈니스 가치)

- 처리 시간 단축: 민원 1건 평균 검토 완료 시간
- 품질 향상: 최종 답변 재수정률, 재민원율
- 신뢰도 향상: citation 포함률, 경고 후 수정 반영률
- 운영 안정성: E2E 완주율, 단계별 실패율

## 10. 데모 완료 체크리스트 (DoD 연계)

1. 민원 1건 선택 시 analyzer 결과가 생성/표시된다.
2. `/search` 결과에 `routing_trace`가 포함되고 UI에서 확인된다.
3. `/qa`가 `routing_hint`를 수신해 답변/citation을 반환한다.
4. 우측 AI 패널에 답변 초안과 citation이 함께 표시된다.
5. 공무원이 초안을 수정하고 검토완료로 전환할 수 있다.
6. 단일/복합/예외 시나리오가 중단 없이 연속 동작한다.

## 11. 부록: 구현 시 권장 이벤트 스키마

```json
{
  "event_name": "qa_review_completed",
  "complaint_id": "CMP-2026-0001",
  "operator_id": "user-001",
  "route_key": "welfare/high",
  "strategy_id": "topic_welfare_high_v1",
  "latency_ms": {
    "analyzer": 48,
    "router": 8,
    "retrieval": 132,
    "generation": 920
  },
  "quality_signals": {
    "citation_coverage": 0.92,
    "hallucination_flag": false,
    "segment_coverage": 1.0
  },
  "edit_signals": {
    "edit_count": 3,
    "edit_distance": 124,
    "regenerated": true
  },
  "final_status": "review_completed",
  "timestamp": "2026-04-09T14:20:00+09:00"
}
```
