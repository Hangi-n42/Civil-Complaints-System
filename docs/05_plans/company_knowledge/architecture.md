# 회사 지식 워크벤치 — 목표 아키텍처·설계

- 문서 버전: v1.7
- 문서 정리·코드 정적 확인일: 2026-09-26
- 상태: K2 자료 계층·K3 온톨로지 초안 구현 및 Mac 확인 완료. 이후 계층은 목표 설계다.

[제품 요구사항](../../00_overview/company_knowledge_prd.md) · [구현 계획](implementation.md) · [마일스톤](milestones.md)

## 설계와 현재 코드의 경계

회사 지식 구축·검수·갱신·Local/Global 검색이 제품의 주기능이다. 기존 민원 시스템은 재사용 기반이며 P1 활용 예시다. 현재 `app/knowledge`, knowledge router, `/knowledge` 화면에 K2 자료 등록·추출·원문 위치 조회가 구현되어 있다. SQLite 원장은 Source/SourceVersion/ParsedBlock/Evidence/parse Run을 저장한다. K3 초안 생성·검토·LinkML 버전도 구현했다. 그래프·활성화·검색은 이후 목표 설계다. [K2 확인 결과](../../30_manuals/knowledge_k2_runbook.md)를 참고한다.

## 1. 현재 구현과 신규 부분

2026-09-27 작업 트리 기준이다. K2·K3는 Mac 실제 API·화면을 확인했으며 Windows 실행은 미확인이다.

| 경계 | 현재 확인 | 이번 요구 |
|---|---|---|
| API | FastAPI, Search/QA/stream·민원 구조화·Intelligence 존재 | 신규 지식 라우터와 별도 계약 |
| 지식 원장 | `app/knowledge`의 K2 자료·K3 온톨로지/결정 원장 구현 | 주장·활성화 계층 추가 |
| 검색 | 운영 service는 Chroma·BM25/RRF 등의 경로. filters가 있으면 hybrid 미사용 | 기존 경로 보존, 비교 실험의 필터 조건 고정 |
| QA 근거 | `SearchInputResult`의 chunk_id/case_id/snippet 필수 | 회사 문서에 가짜 민원 case_id를 부여하지 않음 |
| 평가 | Qwen `qwen3.5:4b`, Q2 / Q3·Q4·Q5 / Q1·Q7 / Q6 / Q0의 5그룹. 재평가 Q2 재사용 시 4호출 | 기존 민원 평가 보존. 회사 지식 정답 평가로 전용하지 않음 |
| 생성·구조화 | 설정 기본값 EXAONE `exaone3.5:7.8b` | 기존 설정 유지 |
| 보안 | 확인한 API/FE에서 사용자 인증·역할 검사 경로를 찾지 못함. API 기본 공개 바인딩·CORS 설정 존재 | P0 loopback 실행을 명시. 기관 다중 사용자 운영은 후속 조건 |

참조 코드: [API main](../../../app/api/main.py), [검색 service](../../../app/retrieval/service.py), [QA 스키마](../../../app/api/schemas/generation.py), [context mapper](../../../app/generation/context_mapper.py), [citation mapper](../../../app/generation/citation/citation_mapper.py), [평가 그룹](../../../app/evaluation/civil_llm_rubric.py), [모델 호출](../../../app/generation/service.py), [환경 설정](../../../app/core/config.py), [FE API](../../../frontend/lib/api.ts).

`RetrievedDoc`은 검색 평가 파이프라인의 계약이다. 운영 검색 결과 또는 QA 입력과 동일한 타입이라고 가정하지 않는다. 기존 `observation/result/request/context`에서 `result`는 피해·결과 문맥이므로 실제 업무 처리 결과로 자동 매핑하지 않는다.

## 2. 최소 구조 제안

```text
허용된 문서·CSV·제공된 시스템 스키마
  → 원문/버전 등록 → 절·표 추출 → 로컬 AI 후보 작성
  → ID·근거 확인 → 사람의 묶음 검토
  → SQLite 지식 원장 + 활성 스냅샷
  → Local 검색/Global 종합·원문 인용·근거 경로·변경 검토
  → P1 민원 워크벤치의 별도 지식 패널
```

- 코어는 `app/knowledge/`, API는 별도 knowledge router, FE는 별도 `/knowledge` 영역을 제안한다. 파일/클래스 수는 구현 시 필요한 만큼만 만든다.
- 저장은 `data/knowledge/knowledge.db`를 기본으로 하고 원문은 로컬 데이터 영역에 둔다. 원문·DB·모델·비밀 값은 Git에 올리지 않는다.
- SQLite에서 개체·관계·근거·버전을 관리한다. 필요할 때 제한된 관계 조회를 수행하며 별도 Neo4j·벡터 DB·메시지 큐를 필수로 추가하지 않는다.
- 기존 Chroma를 활용할 경우 별도 collection과 source_version 필터를 사용하고 기존 민원 collection을 섞지 않는다. DB가 진실의 원장이며 파생 검색 인덱스는 활성 ID를 다시 확인한다.
- 두 검색의 입력과 근거 형식을 공유한다. Global 중간 요약은 요청 안에서만 유지하고 스냅샷·자료 범위·의존 ID를 Run에 기록한다. 원문 인용은 지식 원장에서 조회한다. 응답 전 사용 상태가 바뀐 경우 관련 ID만 재확인한다. 영속 요약 캐시·무효화 서비스·이중 원장은 만들지 않는다.
- 최초 구현은 기존 앱을 띄우는 동안 명시적으로 시작한 단일 작업으로 충분하다. 작업 상태를 남기되 병렬 처리·분산 스케줄러는 도입하지 않는다.


## 3. 책임과 변경 경계

- 자료·파싱: 원본과 추출 실행을 분리하고 위치를 보존한다.
- 스키마·추출: AI 후보와 승인 온톨로지를 분리하고, LinkML 정본에서 추출 계약을 파생한다.
- 원장·검토: 개체·조건·근거·검토 결정과 불변 스냅샷을 SQLite에서 관리한다.
- 검색: 원장의 활성/사용 가능 상태를 기준으로 Local 관계 조회와 Global 종합을 제공한다.
- 민원 연결: 별도 assist 계약으로 연결하며 기존 case_id·Search/QA·평가 계약을 보존한다.

필드·상태·API 기준은 [최소 계약](contracts.md), 라이브러리별 접점은 [구현 계획](implementation.md), 데이터 의미·상태 전이·수용 기준은 [PRD](../../00_overview/company_knowledge_prd.md)에 둔다. 실제 코드가 생기면 구현 범위를 확인한 뒤 현재 계약 문서로 반영한다.

## K3 구현 반영 (2026-09-27)

기존 직렬 Run에 온톨로지 순차 실행을 추가했다. SQLite의 ontology_versions/changesets/decisions에 정본·후보·결정을 저장하고 자료 화면의 온톨로지 탭에서 검토한다. 기존 파싱 상태 갱신은 parse만 수행한다. 지식그래프·활성화·검색은 후속 단계다. [K3 안내](../../30_manuals/knowledge_k3_runbook.md).
