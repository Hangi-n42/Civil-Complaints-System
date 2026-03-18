# Title
[Week 1][FE][도훈] 업로드·검색·챗 화면 와이어프레임 및 데모 사용자 흐름 설계

# Suggested Labels
- frontend
- fe
- week1
- ux
- demo

# Suggested Assignee
- 도훈

# Summary
FE의 1주차 핵심 목표는 사용자가 시스템을 어떻게 사용할지 전체 흐름을 먼저 설계하는 것이다.  
이 단계에서는 코드 구현보다, 업로드→구조화 확인→검색→QA로 이어지는 사용 흐름과 데모 동선을 고정하는 것이 중요하다.

# Source Docs
- [docs/30_manuals/fe_manual.md](../../../30_manuals/fe_manual.md)
- [docs/10_contracts/api/api_spec.md](../../../10_contracts/api/api_spec.md)
- [docs/00_overview/prd.md](../../../00_overview/prd.md)
- [docs/00_overview/mvp_scope.md](../../../00_overview/mvp_scope.md)

# Tasks
- [ ] 업로드 화면 와이어프레임 작성
- [ ] 구조화 결과 확인 화면 와이어프레임 작성
- [ ] 검색 화면 와이어프레임 작성
- [ ] 챗/QA 화면 와이어프레임 작성
- [ ] 대시보드 최소 화면 초안 작성
- [ ] 주요 상태 정의 (`loading`, `success`, `empty`, `error`)
- [ ] 업로드→구조화→검색→QA 전체 사용자 흐름도 작성
- [ ] 데모 시나리오 3종 초안 작성 (`도로안전`, `소음`, `환경`)
- [ ] 화면에 꼭 보여야 할 API 응답 필드 목록 정리
- [ ] BE1/BE2/BE3와 화면 요구 데이터 상호 확인

# Deliverables
- 화면 흐름도
- 업로드/검색/챗 와이어프레임
- 상태 정의 문서
- 데모 UX 시나리오 초안
- 화면별 필요 응답 필드 목록

# Acceptance Criteria
- 팀원이 화면 설계만 봐도 사용자 흐름을 이해할 수 있다.
- 어떤 API 응답이 어떤 컴포넌트에 들어가는지 설명 가능하다.
- 2주차부터 Streamlit 골격 구현에 바로 들어갈 수 있다.

# Collaboration
- BE1: 구조화 결과에서 보여줄 필드와 상태 정의 협의
- BE2: 검색 결과 카드와 QA 응답에 필요한 응답 형식 확인
- BE3: validation/citation/error 정보를 어떻게 보여줄지 협의

# Notes
1주차 FE 산출물은 예쁜 화면보다도, 데모 중 끊기지 않는 사용자 흐름을 만드는 데 목적이 있다.
