# ADR — 아키텍처 결정 기록

> **2026-09-27 병합 상태 보충:** #497의 ADR v3.0과 과거 결정 구분을 유지한다. 아래 ADR-020/021의 자료 계층 미구현 표기는 작성 당시 상태다. #498은 K2 자료 원장·API·화면을 추가했으며 온톨로지·그래프·검색은 미구현이다. [K2 기록](../30_manuals/knowledge_k2_runbook.md) 참조.

- 문서 버전: v3.0
- 기준일: 2026-09-26
- 확인 기준: 로컬 Git `b53134a`와 현재 작업 트리. 원격 최신 상태나 실행 성능을 검증한 문서가 아니다.
- 역할: 기존 민원 구현의 유효 결정과 신규 회사 지식 제품의 설계 결정을 구분한다.
- [주 제품 PRD](company_knowledge_prd.md) · [현재 민원 아키텍처](complaint_system_architecture.md) · [신규 목표 설계](../05_plans/company_knowledge/architecture.md)

## 1. 상태와 증거 기준

**현행**은 현재 코드에서 확인한 선택, **부분 대체**는 기존 결정 일부만 유지, **과거**는 당시 일정·조직·설계 기록, **계획**은 아직 구현되지 않은 제품 방향이다. Git 커밋은 변경의 증거이며 도입 효과·정확도의 증명이 아니다. 현재 작업 트리에는 미커밋 변경이 있어 HEAD와 동일한 상태로 간주하지 않는다.

이전 `ARD-001~016` 식별자는 추적을 위해 유지한다. 이전 문서에서 모든 항목에 붙었던 Active 표기를 그대로 승계하지 않는다. 상세 맥락·대안·당시 수치는 [v2.2 원문](../90_archive/complaint_system/adr_architecture_decision_record_v2.2.md)에 보존한다.

## 2. 기존 결정의 현재 상태

| 기존 ID | 현재 상태 | 현재 결정·변경 이유 | 확인 근거 |
|---|---|---|---|
| ARD-001 로컬 우선 | 현행 | Ollama 기반 생성·평가와 로컬 검색 유지. 로컬 실행만으로 개인정보 보호가 보장되는 것은 아니며 기존 PII 처리를 함께 사용 | `app/core/config.py`, `app/generation/service.py`, `src/pii/` |
| ARD-002 모듈 분리 | 현행·확장 | 기존 ingestion/structuring/retrieval/generation/api/ui에 evaluation·complaint_intelligence와 별도 frontend가 존재 | `app/`, `frontend/` |
| ARD-003 FastAPI+Streamlit | 부분 대체 | 주 FE는 Next.js. Streamlit 소스는 기존 UI로 남으며 제거된 것으로 기록하지 않음. 당시 선택은 ARD-013으로 대체 | `frontend/package.json`, `app/ui/Home.py` |
| ARD-004 스키마·검증 우선 | 현행 | Pydantic/API 계약과 구조화 검증을 유지. 회사 문서를 기존 민원 case_id 계약에 억지로 맞추는 것은 신규 설계에서 제외 | `app/api/schemas/`, `app/structuring/schemas.py`, 신규 PRD |
| ARD-005 응답 래퍼 | 기존 계약 | 기존 API의 응답·오류 계약 참고. 신규 지식 API의 세부 계약 확정은 K1 잔여 작업이며 모든 미래 API까지 구현 완료로 취급하지 않음 | [현재 API 계약](../10_contracts/api/current_api_contract.md), `app/api/main.py` |
| ARD-006 시각 정책 | 기존 계약 | KST 출력 정책의 기존 근거를 보존. 모든 datetime 경로의 준수 여부를 이번 문서 작업에서 전수 검증하지 않음 | [데이터 계약](../10_contracts/data/current_data_contract.md) |
| ARD-007 BGE-M3+Chroma | 현행·확장 | 임베딩 기본값 BAAI/bge-m3 유지. 검색 기본 전략은 hybrid이며 BM25 결합 경로가 추가됨. 필터가 있으면 hybrid 분기 미사용 | `app/core/config.py`, `app/retrieval/service.py` |
| ARD-008 Adaptive 단계 도입 | 부분 대체 | 분석·routing trace는 유지하되 모든 질의에 복잡도별 검색 파라미터가 적용된다는 과거 설명은 현행과 다름 | `app/api/routers/retrieval.py`의 `fixed_search_hint` |
| ARD-009 관측·평가 | 현행·확장 | 검색/생성 평가·민원 온라인 rubric·관제 평가가 별도로 존재. 서로 다른 점수와 평가 데이터는 합쳐 해석하지 않음 | `app/evaluation/`, `scripts/evaluate_qa.py`, [평가 안내](../30_manuals/evaluation_runbook.md) |
| ARD-010 역할 오너십 | 과거 | FE/BE1/BE2/BE3 4인 운영 기록. 현재 담당자 배정 근거가 아니며 새 담당자를 추정하지 않음 | v2.2 원문 |
| ARD-011 데모 UX | 과거 설계·일부 구현 | UI가 존재하나 당시 모든 경고·상태·완료 조건이 구현됐다고 포괄 선언하지 않음 | `frontend/app/workbench/`, [과거 시나리오](../90_archive/complaint_system/adaptive_rag_workbench_user_scenario.md) |
| ARD-012 Week2 동결 | 과거 | Week2 우선순위는 당시 통합 규칙. 신규 개발은 새 PRD와 확정할 지식 API 계약을 기준으로 함 | [문서 지도](../README.md) |
| ARD-013 Next.js 전환 | 현행 | FastAPI와 Next.js 분리. 현재 Workbench·Intelligence 화면 및 초안 편집 구현을 보존 | `frontend/app/`, 커밋 `8c04b66` |
| ARD-014 복잡도 분석 | 현행·적용 제한 | Topic/Complexity 분석은 유지. 검색 API의 top_k는 요청값, snippet은 1100, chunk policy는 balanced로 고정하므로 분석과 실행 전략을 구별 | `app/api/routers/retrieval.py`, `app/retrieval/analyzers/` |
| ARD-015 Rule+LLM 구조화 | 현행·갱신 | entity/LLM 추출과 merger 분리. 구조화 모델 기본값은 exaone3.5:7.8b이며 과거 exaone3 설정을 실행 기준으로 사용하지 않음 | `app/structuring/llm_extractor.py`, `app/structuring/merger.py`, `app/core/config.py` |
| ARD-016 TopicAnalyzer 분리 | 현행 | 독립 분석 모듈 유지. 당시 확장 계획·성능 기대를 현재 성과로 간주하지 않음 | `app/retrieval/analyzers/topic_analyzer.py` |

## 3. 후속 구현에서 확인한 결정

### ADR-017: 민원 생성·평가 모델 분리 — 현행

- 결정: 생성·재작성은 EXAONE `exaone3.5:7.8b`, 온라인 Q0~Q7 평가는 Qwen `qwen3.5:4b`를 기본으로 사용한다.
- 평가 그룹: Q2 / Q3·Q4·Q5 / Q1·Q7 / Q6 / Q0. 정상 최초 평가 5회, 같은 요청에서 민원·근거가 같아 Q2를 재사용하면 재평가 4회다. 요청 간 캐시는 의미하지 않는다.
- 이유·제약: 생성 설정을 유지하면서 평가를 분리한다. 기존 인용·형식 검증과 재작성 흐름을 보존한다. 이 문서 최신화에서 모델 우열·정확도를 다시 측정하지 않았다.
- 근거: `b53134a`(2026-09-17), `app/evaluation/civil_llm_rubric.py`, `app/core/config.py`.

### ADR-018: 관제를 별도 read-model로 분리 — 현행

- 결정: Complaint Intelligence의 급증 알림·기관 인사이트·중복 민원 상태는 별도 서비스·repository로 관리한다. SQLite 구현과 InMemory 구현이 존재한다.
- 의미: 후보·확인·분리·반려는 내부 상태이며 외부 민원 시스템의 실제 병합·발송을 의미하지 않는다. 대표 답변 초안 생성과 FE 편집 흐름은 기존 구현으로 유지한다.
- 근거: `c97f5e9`(2026-06-21), `8c04b66`(2026-06-22), `app/complaint_intelligence/service.py`, `repository.py`, `sqlite_repository.py`.
- 제약: 현재 지식 원장과 동일한 DB·도메인으로 간주하지 않는다.

### ADR-019: 검색 근거에 상담사 답변을 별도 전달 — 현행

- 결정: 상담사 답변을 전용 필드로 색인·검색 결과에 전달한다. 질의 분석 trace와 실제 검색 파라미터 적용은 구분한다.
- 근거: `9a5ae5d`(2026-06-22), `app/retrieval/service.py`, `app/retrieval/vectorstores/chroma_store.py`.
- 제약: 필드가 존재한다는 사실이 답변의 현행 법령 적합성·정답성을 보장하지 않는다.

## 4. 신규 제품 결정 — 계획, 미구현

### ADR-020: 회사 지식 제품을 핵심으로 전환

- 결정: 회사 지식 온톨로지·그래프 구축, 사람 검토, 갱신, Local/Global 검색을 주 기능으로 삼고 기존 민원 기능은 재사용 기반 및 P1 활용 예시로 둔다.
- 근거: [회사 지식 PRD v1.4](company_knowledge_prd.md). Git 커밋된 구현 결정과 구분되는 현재 제품 요구다.
- 경계: `app/knowledge`, 지식 전용 라우터·화면은 현재 없다. 기존 Search/QA 응답 계약을 훼손하지 않고 별도 지식 계약을 확정한다.

### ADR-021: SQLite 지식 원장·근거·스냅샷 중심의 최소 구현

- 결정: 출처·문서 버전·근거·후보·검토·주장·관계·불변 snapshot과 별도 사용 상태를 관리하는 설계다. Local은 대상 관계와 원문, Global은 선택 범위의 활성 지식을 사용한다.
- 이유: 원문 추적과 변경 영향을 관리하면서 현재 파일럿 범위를 구현한다. 거대한 그래프 플랫폼 도입이나 논문 전체 재현을 완료 조건으로 삼지 않는다.
- 도입·이식 범위는 [구현 계획](../05_plans/company_knowledge/implementation.md)을 따른다. 후보 라이브러리를 이미 설치·검증한 것으로 해석하지 않는다.
- 현재 준비: 파일럿 자료·12개 과제 고정은 K1 부분 완료다. 비교 측정 절차·최소 데이터/API 계약·제품 구현은 남아 있다. 새 과제도 AI·설계자에게 노출됐으며 독립 인간 맹검 자료가 아니다.

## 5. 변경 규칙

결정을 바꿀 때 기존 ID·근거·대체 관계를 남긴다. 계획을 현행으로 바꾸려면 실제 코드·관련 확인 결과를 추가한다. 구현 완료와 품질·효용 입증은 별도로 기록한다. 이번 갱신은 Git 이력·소스 정적 대조이며 테스트·서버·Windows 실행은 수행하지 않았다.
