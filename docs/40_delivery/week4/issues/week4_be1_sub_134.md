# Title
[Week 4][BE1][Sub] 구조화/메타데이터 품질 점검표 배포 #134

# Suggested Labels
- backend
- be1
- week4
- quality
- handoff

# Suggested Assignee
- 현기

# Parent Issue
- [Week 4][BE1][Main] baseline 평가셋/지표 운영 및 KPI 정리 #127

# Summary
Week4 BE1 서브 이슈 #134이다.

목표는 구조화/메타데이터 품질 점검표를 팀 공용 기준으로 배포해
Gate A 지표 산출 가능 상태를 안정적으로 유지하는 것이다.

주의: 현재 운영 기준상 KPI "초안 문서"는 별도 산출물로 만들지 않는다.

# Source Docs
- [docs/30_manuals/be1_manual.md](../../../30_manuals/be1_manual.md)
- [docs/00_overview/prd.md](../../../00_overview/prd.md)
- [docs/00_overview/wbs_8weeks_v2_updated.md](../../../00_overview/wbs_8weeks_v2_updated.md)
- [docs/10_contracts/interfaces/week4/week4_be1_interface.md](../../../10_contracts/interfaces/week4/week4_be1_interface.md)
- [docs/10_contracts/interfaces/week4/week4_common_interface.md](../../../10_contracts/interfaces/week4/week4_common_interface.md)

# Scope
- 구조화 품질 점검 항목 정의/배포
- 메타데이터 품질 점검 항목 정의/배포
- Gate A 측정 항목 산출 가능 상태 점검 절차 정리

# Deliverables
- 구조화 품질 점검표(필드별 점검 기준)
- 메타데이터 품질 점검표(`region`, `category`, `created_at` 중심)
- Gate A 산출 가능 상태 체크 결과(스크립트/로그 경로 포함)

# Artifact Paths
- `docs/40_delivery/week4/be1/week4_structured_metadata_quality_checklist.md`
- `docs/40_delivery/week4/be1/week4_gatea_metric_readiness_check.md`
- `logs/evaluation/week4/be1/week4_metadata_quality_snapshot.json`
- `logs/evaluation/week4/be1/week4_gatea_metric_readiness.json`

# Out of Scope
- KPI 초안 문서 작성/배포는 수행하지 않는다.

# Handoff
- BE2: 검색 필터 품질 기준 공유
- BE3: citation 정합성/파싱 검증 입력 기준 공유
- FE: 데모 검증용 기준 사례 및 실패 샘플 공유

# Completion Rule
- 본문에는 체크박스 완료 기준을 두지 않는다.
- 이슈 완료 시 반드시 코멘트로 근거 산출물을 남긴다.
- 완료 코멘트에는 최소 3가지를 포함한다:
  1) 산출물 파일 경로
  2) 실행 커맨드 또는 검증 절차
  3) 결과 요약(성공/제약/후속 필요사항)

# Notes
- #134 작업 결과는 #127 완료 코멘트 근거로 재사용한다.
- Sub 이슈 단독 PR 가능하도록 변경 파일 범위를 최소화한다.
