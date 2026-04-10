# Week 6 인터페이스 인덱스

기준일: 2026-04-10  
범위: Topic/Multi 분기 확장, PromptFactory/normalize_response 통합

---

## Week 6 핵심 변경사항

### 입출력 변화
- BE1 analyzer 출력을 `{topic_type, complexity_level, complexity_score, complexity_trace, request_segments}`로 통일한다.
- BE2 retrieval trace에 `route_key`, `applied_filters`, `segment_count`, `merge_policy`를 포함한다.
- BE3 `/qa` 응답에서 `structured_output`을 실사용 가능한 형태로 고정한다.

### 데이터 흐름
```
Input Query
    ↓
TopicAnalyzer + ComplexityAnalyzer + Segmenter (BE1)
    ↓
AdaptiveRouter + Topic-aware Retrieval (BE2)
    ↓
routing_hint + retrieval_trace
    ↓
PromptFactory.build(...) (BE3)
    ↓
normalize_response(...)
    ↓
Unified QAResponse (FE 렌더)
```

---

## Week 6 인터페이스 문서

| 문서 | 담당 | 목적 |
| --- | --- | --- |
| [week6_fe_interface.md](week6_fe_interface.md) | FE | 단일/복합 요청 UI 분기, topic/strategy 뱃지 고정 |
| [week6_be1_interface.md](week6_be1_interface.md) | BE1 | topic/complexity 통합 analyzer 출력 계약 |
| [week6_be2_interface.md](week6_be2_interface.md) | BE2 | topic-aware retrieval 분기, segment 병합/trace 계약 |
| [week6_be3_interface.md](week6_be3_interface.md) | BE3 | PromptFactory + normalize_response unified output 계약 |

---

## 상속 규칙

- API 필드 우선순위: `docs/60_specs/api_interface_spec.md`
- 타입 규약 우선순위: `docs/60_specs/data_schema_spec.md`
- Week5 계약은 하위 호환으로 유지하되, Week6 키가 충돌 시 우선한다.

---

## Week 6 체크 포인트

| 항목 | 완료 조건 | 상태 |
| --- | --- | --- |
| Analyzer 통일 | 필수 5키 누락 없이 생성 | ⏳ 진행중 |
| Retrieval trace 확장 | route_key/applied_filters 포함 | ⏳ 진행중 |
| Unified output | structured_output 일관 반환 | ⏳ 진행중 |
| FE 분기 렌더 | request_segments 기반 단일/복합 분기 | ⏳ 진행중 |
