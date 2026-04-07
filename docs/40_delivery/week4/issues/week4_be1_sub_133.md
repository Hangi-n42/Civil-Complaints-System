# Title
[Week 4][BE1][Sub] baseline 평가셋/질문셋 freeze 및 품질 점검 #133

# Suggested Labels
- backend
- be1
- week4
- evaluation
- data-quality

# Suggested Assignee
- 현기

# Parent Issue
- [Week 4][BE1][Main] baseline 평가셋/지표 운영 및 KPI 정리 #127

# Summary
Week4 BE1 서브 이슈 #133이다.

목표는 baseline 평가셋/질문셋을 Week4 기준으로 freeze 상태로 운영하고,
분포/결측/추적 가능성을 점검해 Gate A 입력 데이터 품질을 보장하는 것이다.

# Source Docs
- [docs/30_manuals/be1_manual.md](../../../30_manuals/be1_manual.md)
- [docs/00_overview/prd.md](../../../00_overview/prd.md)
- [docs/00_overview/wbs_8weeks_v2_updated.md](../../../00_overview/wbs_8weeks_v2_updated.md)
- [docs/10_contracts/interfaces/week4/week4_be1_interface.md](../../../10_contracts/interfaces/week4/week4_be1_interface.md)
- [docs/10_contracts/interfaces/week4/week4_common_interface.md](../../../10_contracts/interfaces/week4/week4_common_interface.md)

# Scope
- baseline 평가셋/질문셋 freeze 버전 고정
- freeze manifest 정보 점검(건수/분포/버전/시각)
- 샘플링 기반 품질 점검(필드 결측, 형식, 범주 일관성)

# Deliverables
- freeze 버전 선언 문서 또는 manifest 파일 경로
- 평가셋/질문셋 품질 점검 결과 요약
- Gate A 입력 데이터 사용 가능 판정 결과

# Verification
- 데이터 건수 일치(목표 500건)
- 분포 균형 여부(category/region/difficulty)
- 필수 메타키(`region`, `category`, `created_at`) 결측 여부
- request_id/trace 연결 가능 여부

# Completion Rule
- 본문에는 체크박스 완료 기준을 두지 않는다.
- 이슈 완료 시 반드시 코멘트로 근거 산출물을 남긴다.
- 완료 코멘트에는 최소 3가지를 포함한다:
  1) 산출물 파일 경로
  2) 실행 커맨드 또는 검증 절차
  3) 결과 요약(성공/제약/후속 필요사항)

# Notes
- #133 작업 결과는 #127 완료 코멘트 근거로 재사용한다.
- Sub 이슈 단독 PR 가능하도록 변경 파일 범위를 최소화한다.
