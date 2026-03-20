# Week 2 GitHub 이슈 인덱스

기준일: 2026-03-19  
라벨: `week2`
문서 버전 변경 로그: 2026-03-20 `week2_common_interface.md` v1.2, `week2_be1_interface.md` v1.1로 코드 정합 반영

## 1) 상태 요약

- Parent 이슈 5개 생성 완료
- Sub 이슈 15개 생성 완료
- Parent 본문 체크리스트에 Sub 이슈 링크 반영 완료

## 2) Parent 이슈

| 구분 | Issue # | 제목 | URL |
| --- | --- | --- | --- |
| Common | #12 | [Week 2][Common] ingest-structure-validate E2E 안정화 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/12 |
| BE1 | #13 | [Week 2][BE1] 정제·PII·4요소 구조화 품질 고도화 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/13 |
| BE2 | #14 | [Week 2][BE2] 구조화 결과 인덱싱 입력 포맷 고정 및 매핑 검증 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/14 |
| BE3 | #15 | [Week 2][BE3] /ingest,/structure API 검증·파싱 안정화 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/15 |
| FE | #16 | [Week 2][FE] 업로드·구조화 결과·검증 상태 UI 안정화 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/16 |

## 3) Sub 이슈 맵

### 3.1 Common (Parent #12)

| Sub # | 제목 | URL |
| --- | --- | --- |
| #17 | [Week 2][Common][Sub-1] API I/O 계약 재검토 및 동결 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/17 |
| #18 | [Week 2][Common][Sub-2] 샘플 50건 기준 E2E 체크리스트 운영 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/18 |
| #19 | [Week 2][Common][Sub-3] 주간 리스크 로그 및 사인오프 템플릿 적용 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/19 |

### 3.2 BE1 (Parent #13)

| Sub # | 제목 | URL |
| --- | --- | --- |
| #20 | [Week 2][BE1][Sub-1] ingestion 정제/PII/중복 처리 규칙 고도화 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/20 |
| #21 | [Week 2][BE1][Sub-2] structuring 4요소 추출 후처리 규칙 보완 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/21 |
| #22 | [Week 2][BE1][Sub-3] 구조화 품질 측정 스크립트/리포트 정리 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/22 |

### 3.3 BE2 (Parent #14)

| Sub # | 제목 | URL |
| --- | --- | --- |
| #23 | [Week 2][BE2][Sub-1] 구조화 결과 -> 인덱싱 입력 포맷 변환 규격화 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/23 |
| #24 | [Week 2][BE2][Sub-2] 검색 메타데이터 매핑 검증 및 필터 키 확정 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/24 |
| #25 | [Week 2][BE2][Sub-3] index 전 샘플셋 유효성 자동 점검 스크립트 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/25 |

### 3.4 BE3 (Parent #15)

| Sub # | 제목 | URL |
| --- | --- | --- |
| #26 | [Week 2][BE3][Sub-1] /ingest,/structure 에러코드/검증 포맷 일치화 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/26 |
| #27 | [Week 2][BE3][Sub-2] JSON 파싱/검증 공통 유틸 정리 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/27 |
| #28 | [Week 2][BE3][Sub-3] API 회귀 테스트 케이스 보강 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/28 |

### 3.5 FE (Parent #16)

| Sub # | 제목 | URL |
| --- | --- | --- |
| #29 | [Week 2][FE][Sub-1] 업로드/구조화 결과 화면 상태표시 개선 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/29 |
| #30 | [Week 2][FE][Sub-2] 검증 상태 배지/에러 메시지 UX 정리 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/30 |
| #31 | [Week 2][FE][Sub-3] 50건+ 처리 데모 흐름 점검 체크리스트 | https://github.com/Hangi-n42/AI-Civil-Affairs-Systems/issues/31 |

## 4) Week 2 완료 기준 (WBS 연동)

- 샘플 50건+ 처리
- 스키마 통과율 90% 목표
- 구조화 평가 파이프라인 재실행 가능

## 5) 추적 규칙

- Sub 이슈 완료 후 Parent 체크리스트 갱신
- 금요일 점검 시 Parent 이슈 기준으로 진척률 보고
- Week 2 종료 시 본 문서에 `완료/미완료/이관` 상태 업데이트

## 6) Week 2 인터페이스 문서

변수명/포맷/객체명 충돌 방지를 위해 아래 문서를 Week 2 구현 기준으로 사용한다.

- 인덱스: `docs/10_contracts/interfaces/week2/README.md`
- 공통 규약: `docs/10_contracts/interfaces/week2/week2_common_interface.md`
- BE1: `docs/10_contracts/interfaces/week2/week2_be1_interface.md`
- BE2: `docs/10_contracts/interfaces/week2/week2_be2_interface.md`
- BE3: `docs/10_contracts/interfaces/week2/week2_be3_interface.md`
- FE: `docs/10_contracts/interfaces/week2/week2_fe_interface.md`

## 7) Week 2 BE1 점검 산출물

- BE1 이슈 체크리스트 diff 점검: `docs/40_delivery/week2/be1_diff_checklist.md`
