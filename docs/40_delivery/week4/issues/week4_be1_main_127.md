# Title
[Week 4][BE1][Main] baseline 평가셋/지표 운영 및 KPI 정리 #127

# Suggested Labels
- backend
- be1
- week4
- evaluation
- quality

# Suggested Assignee
- 현기

# Summary
Week4 BE1 부모 이슈다.

Week4에서 BE1은 baseline 평가셋/질문셋 운영 기준을 고정하고,
구조화/메타데이터 품질 점검 체계를 통해 Gate A 지표 산출 가능 상태를 유지한다.

주의: 현재 팀 운영 기준상 KPI "초안 문서"는 별도 산출물로 만들지 않는다.

# Source Docs
- [docs/30_manuals/be1_manual.md](../../../30_manuals/be1_manual.md)
- [docs/00_overview/prd.md](../../../00_overview/prd.md)
- [docs/00_overview/wbs_8weeks_v2_updated.md](../../../00_overview/wbs_8weeks_v2_updated.md)
- [docs/10_contracts/interfaces/week4/week4_be1_interface.md](../../../10_contracts/interfaces/week4/week4_be1_interface.md)
- [docs/10_contracts/interfaces/week4/week4_common_interface.md](../../../10_contracts/interfaces/week4/week4_common_interface.md)

# Scope
- baseline 평가셋/질문셋 freeze 상태 운영 고정
- 구조화/메타데이터 품질 점검 수행
- Gate A 지표 산출 가능 상태 유지(산출 파이프라인/로그/근거 경로 확인)

# Linked Sub Issues
- [Sub #133 - baseline 평가셋/질문셋 freeze 및 품질 점검](./week4_be1_sub_133.md)
- [Sub #134 - 구조화/메타데이터 품질 점검표 배포](./week4_be1_sub_134.md)

# Deliverables
- 평가셋 freeze 근거 및 버전 정보
- 구조화/메타데이터 품질 점검표
- Gate A 지표 산출 가능 상태 근거(스크립트/로그 경로)
- 이슈 종료 코멘트용 근거 산출물 목록

# Completion Rule
- 본문에는 체크박스 완료 기준을 두지 않는다.
- 이슈 완료 시 반드시 코멘트로 근거 산출물을 남긴다.
- 완료 코멘트에는 최소 3가지를 포함한다:
  1) 산출물 파일 경로
  2) 실행 커맨드 또는 검증 절차
  3) 결과 요약(성공/제약/후속 필요사항)

# Collaboration
- BE2: 검색 필터용 메타키 품질 기준 동기화
- BE3: Gate A 지표 산출 입력/검증 규칙 동기화
- FE: 데모 검증용 기준 질의/실패 샘플 전달

# Notes
- #127은 부모 이슈로 운영하며, 실제 구현/검증은 #133, #134 단위로 분리 진행한다.
- Sub 이슈 단위로 PR을 열 수 있도록 커밋 범위를 분리한다.
