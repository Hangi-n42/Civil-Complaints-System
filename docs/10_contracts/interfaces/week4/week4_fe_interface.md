# Week 4 FE 인터페이스 문서 (Transition Note)

문서 버전: v1.1-week4-final  
최신화: 2026-04-09

## 1. 문서 목적

본 문서는 Week4 종료 시점의 FE 계약을 기록하며, Week5부터는 Next.js Workbench 아키텍처 기준으로 확장한다.

## 2. Week4 확정 계약

- SearchResponse: `results[]`, `total_found`, `elapsed_ms`
- QAResponse: `answer`, `citations[]`, `limitations`, `latency_ms`

## 3. Week5+ 확장 필드 (호환 추가)

- SearchResponse:
  - `routing_trace.length_bucket`
  - `routing_trace.topic_type`
  - `routing_trace.is_multi`
  - `routing_trace.strategy_id`
- QAResponse:
  - `routing_trace`
  - `structured_output`

## 4. FE 구현 메모

- Week4 Streamlit 계약은 레거시 호환용으로 유지한다.
- Week5 이후 실제 데모 구현은 Next.js Workbench에서 수행한다.
- 신규 화면은 3단 분할(좌 네비게이션/중앙 목록/우 AI 패널) 구조를 따른다.
