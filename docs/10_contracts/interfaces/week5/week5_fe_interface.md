# Week 5 FE 인터페이스 문서

문서 버전: v1.0-week5-draft  
작성일: 2026-04-10  
책임: FE  
협업: BE3, BE2

---

## 1) 책임 범위

Week 5에서 FE는 Search 단계의 adaptive 라우팅 정보를 사용자에게 설명 가능하게 노출하고, Search->QA 전환 시 라우팅 힌트를 손실 없이 전달한다.

주요 작업:
1. 3단 Workbench 스캐폴딩(좌/중/우)
2. complexity/strategy UI 표출
3. `/qa` 요청에 `routing_hint` 필수 포함

---

## 2) 입력 계약 (BE3 -> FE)

### 2.1 SearchResponse.data 필수 필드
- `complaint_id: string`
- `strategy_id: string`
- `route_key: string`
- `routing_hint: RoutingHint`
- `routing_trace: RoutingTrace`
- `retrieved_docs: RetrievedDoc[]`

### 2.2 RoutingTrace 필수 표시 키
- `topic_type`
- `complexity_level`
- `complexity_score`
- `complexity_trace`
- `route_reason` (선택이지만 표시 권장)

### 2.3 카드/패널 최소 렌더 키
- 중앙 카드: `complexity_level`, `complexity_score`, `strategy_id`
- 우측 패널: `route_key`, `route_reason`, `complexity_trace`

---

## 3) 상태 저장 계약 (FE 내부)

```ts
interface SearchSessionState {
  complaintId: string;
  strategyId: string;
  routeKey: string;
  routingHint: {
    strategy_id: string;
    route_key: string;
    top_k: number;
    snippet_max_chars: number;
    chunk_policy: string;
  };
  routingTrace: {
    topic_type: string;
    complexity_level: string;
    complexity_score: number;
    complexity_trace: Record<string, number | boolean>;
    route_reason?: string;
  };
  retrievedDocs: Array<{
    doc_id: string;
    snippet: string;
    score: number;
  }>;
}
```

필수 규칙:
- 상태 저장 시 `strategyId === routingHint.strategy_id` 이어야 한다.
- 상태 저장 시 `routeKey === routingHint.route_key` 이어야 한다.
- 상태 저장 실패 시 QA 버튼 비활성화한다.

---

## 4) 출력 계약 (FE -> BE3)

### 4.1 POST /qa 요청 필수 구조

```json
{
  "complaint_id": "CMP-2026-0001",
  "query": "임대주택 보수 지연과 관리비 이의제기 관련 민원",
  "routing_hint": {
    "strategy_id": "topic_welfare_high_v1",
    "route_key": "welfare/high",
    "top_k": 9,
    "snippet_max_chars": 1100,
    "chunk_policy": "expanded"
  },
  "retrieved_docs": [
    {
      "doc_id": "DOC-001",
      "snippet": "관리비 이의제기 처리 절차...",
      "score": 0.89
    }
  ]
}
```

검증 규칙:
- `routing_hint` 누락 시 요청 금지
- `routing_hint.route_key`는 `^[a-z_]+/(low|medium|high)$` 패턴 권장
- `retrieved_docs` 미존재 허용, 단 Search 연계 흐름에서는 전달 권장

---

## 5) UI 상태/에러 계약

상태 4종:
- `loading`: Search 또는 QA 호출 중
- `success`: 라우팅/답변 정상 렌더
- `error`: API 오류 또는 계약 검증 실패
- `empty`: 검색 결과 없음 또는 선택 민원 없음

Week5 FE 에러 코드 매핑:
- `VALIDATION_ERROR`: 입력 필드 누락
- `ROUTING_HINT_MISSING`: FE 사전검증 실패(로컬 코드)
- `NETWORK_ERROR`: API 통신 실패

---

## 6) 핸드오프

BE3로 전달:
- FE에서 실제 사용 중인 `/qa` 요청 payload 샘플
- `routing_hint` 누락 재현 케이스

BE2로 전달:
- 사용자에게 노출된 route_key/strategy_id 조합 리스트

완료 체크:
- Search->QA 전환 시 동일 `strategy_id` 유지
- complexity 필드가 카드/패널 모두에서 보임
