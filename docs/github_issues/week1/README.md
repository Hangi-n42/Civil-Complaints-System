# Week 1 GitHub 이슈 생성 기록

## 상태
✅ **완료**: 2026-03-11, 모든 Week 1 이슈 5개 원격 생성 완료

## 생성된 이슈 목록

| Issue # | Title | Assignee | Labels | URL |
|---------|-------|----------|--------|-----|
| #2 | [Week 1][Common] MVP 기준선 정리 및 인터페이스 1차 동결 | 전체 팀 | documentation, planning, common, week1 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/2 |
| #3 | [Week 1][BE1][현기] 데이터 입력 규격·정제 규칙·구조화 평가 기준 초안 | BE1 | backend, be1, data, structuring, week1 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/3 |
| #4 | [Week 1][BE2][민건] 임베딩·벡터DB 후보 비교 및 Ollama/RAG API 입력 구조 | BE2 | backend, be2, retrieval, rag, week1 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/4 |
| #5 | [Week 1][BE3][현석] 스키마 검증 규칙·JSON 파싱·성능/OOM 기준 초안 | BE3 | backend, be3, validation, performance, week1 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/5 |
| #6 | [Week 1][FE][도훈] 업로드·검색·챗 화면 와이어프레임 및 데모 사용자 흐름 | FE | frontend, ux, demo, week1, fe | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/6 |

## 참고: 이슈 생성 자동화 스크립트
`create_week1_issues.ps1`: Week 2~8 이슈 생성 시 재사용 가능한 PowerShell 자동화 스크립트 (25개 라벨 팔레트 포함)

---

## Week 1 마감 정리 (BE2 기준)

기준일: 2026-03-17

### 1) 완료 항목

- [x] 임베딩 후보 비교 계획 수립
	- 산출물: [docs/retrieval/embedding_comparison.md](../../retrieval/embedding_comparison.md)
- [x] ChromaDB/FAISS 비교 및 1차 선택안 제시
	- 산출물: [docs/retrieval/vectordb_comparison.md](../../retrieval/vectordb_comparison.md)
- [x] 검색 메타데이터 키 정의
	- 산출물: [docs/retrieval/metadata_schema.md](../../retrieval/metadata_schema.md)
- [x] 청크 메타데이터 구조 초안
	- 산출물: [docs/retrieval/chunk_schema.md](../../retrieval/chunk_schema.md)
- [x] Ollama 설치/로컬 실행/연동 가능 여부 확인
	- 산출물: [docs/retrieval/ollama_setup_note.md](../../retrieval/ollama_setup_note.md)
- [x] RAG API 입력/출력 초안 및 스키마 반영
	- 산출물: [docs/api_spec.md](../../api_spec.md), [docs/schema_contract.md](../../schema_contract.md)

### 2) 협업 정리 상태

- [x] FE 요구 검색 카드 필드 반영 완료
	- 필수 필드: `doc_id`, `score`, `title`, `snippet`
	- 반영 근거: [docs/api_spec.md](../../api_spec.md)
- [x] BE3 통합 QA 응답 포맷 반영 완료
	- 상태값, citation 토큰, error/meta/validation 구조 반영
	- 반영 근거: [docs/be3_fe_be2_unified_spec.md](../../be3_fe_be2_unified_spec.md), [docs/be2_be3_interface.md](../../be2_be3_interface.md)

### 3) Week 1 종료 전 확인 필요(사인오프)

- [ ] FE: 실제 View 2 검색 카드 렌더링 확인 (필드명/길이/점수 포맷)
- [ ] BE3: `/qa` 실응답 샘플 기준 파서 매칭 확인
- [ ] BE1: 구조화 결과 전달 필드(`case_id`, `created_at`, `source`) 최종 확인

### 4) 리스크 메모 (Week 2 이관)

- 로컬 CPU 환경에서 `/api/v1/qa` JSON 파싱 불안정 케이스가 간헐 발생
- 현재 대응: 파싱 실패 시 폴백 응답 + `qa_validation.warnings` 반환
- 조치 계획: Week 2에서 프롬프트/재시도/모델 경량화 튜닝
