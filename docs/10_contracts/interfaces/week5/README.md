# Week 5 인터페이스 인덱스

기준일: 2026-04-10  
범위: Complexity 기반 Adaptive 분기 1차 구현, Search->QA 전략 연동

---

## Week 5 핵심 변경사항

### 입출력 변화
- `/search` 응답에 `strategy_id`, `route_key`, `routing_trace`, `routing_hint`를 필수화한다.
- `/qa` 요청에 `routing_hint`를 필수화한다.
- `/qa` 응답에 `routing_trace`, `structured_output` 골격을 선반영한다.

### 데이터 흐름
```
Complaint/Text Input
        ↓
BE1 Analyzer Adapter (complexity)
        ↓
BE2 AdaptiveRouter (topic + complexity)
        ↓
/search Response (routing_trace + routing_hint)
        ↓
/qa Request (routing_hint required)
        ↓
QAResponse Skeleton (routing_trace + structured_output)
```

---

## Week 5 인터페이스 문서

| 문서 | 담당 | 목적 |
| --- | --- | --- |
| [week5_fe_interface.md](week5_fe_interface.md) | FE | complexity 라우팅 표시, Search->QA 상태 전달 계약 |
| [week5_be1_interface.md](week5_be1_interface.md) | BE1 | complexity analyzer 입력/출력 어댑터 계약 |
| [week5_be2_interface.md](week5_be2_interface.md) | BE2 | adaptive router 1차 라우팅 및 retrieval 파라미터 계약 |
| [week5_be3_interface.md](week5_be3_interface.md) | BE3 | `/search` trace 통합, `/qa` hint 검증 및 응답 골격 계약 |

---

## 상속 규칙

- API 래퍼 규약: `docs/60_specs/api_interface_spec.md`를 따른다.
- 데이터 키 규약: `docs/60_specs/data_schema_spec.md`를 따른다.
- 라우팅 기준 키: `topic_type`, `complexity_level`, `complexity_score`를 고정한다.
- `length_bucket`, `is_multi`는 보조 표시에만 사용한다.

---

## Week 5 체크 포인트

| 항목 | 완료 조건 | 상태 |
| --- | --- | --- |
| Router 1차 동결 | route_key 포맷 `{topic_type}/{complexity_level}` 적용 | ⏳ 진행중 |
| Search->QA 전략 일치 | 동일 `strategy_id`가 양 API에 노출 | ⏳ 진행중 |
| FE 라우팅 가시화 | complexity/strategy 필드 렌더 확인 | ⏳ 진행중 |
| QA 계약 선반영 | `routing_hint` 검증 + 응답 골격 동작 | ⏳ 진행중 |
