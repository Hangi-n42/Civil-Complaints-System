# Workspace Default Copilot Instructions

이 파일은 본 워크스페이스의 기본 지시 파일이다.

기본 오케스트레이터 프롬프트:
- .github/agents/main_instruction.prompt.md

에이전트 역할 매핑:
- .github/agents/main_instruction.prompt.md: 오케스트레이터 + 프롬프트 미들웨어
- .github/agents/part_agent.prompt.md: 해석/후보 제안
- .github/agents/work_agent.prompt.md: 실행/검증/증빙

기본 동작 규칙:
1. 모든 태스크는 main_instruction 규칙을 기본으로 따른다.
2. 모드 배정, assertion 출력, 이벤트 로그 형식은 main_instruction 규칙을 우선 적용한다.
3. 분해/초안 단계는 part_agent 규칙을, 실행/검증 단계는 work_agent 규칙을 적용한다.
4. 규칙 충돌 시 우선순위는 아래와 같다.
   - 1순위: 이 파일
   - 2순위: .github/agents/main_instruction.prompt.md
   - 3순위: .github/agents/part_agent.prompt.md, .github/agents/work_agent.prompt.md

운영 메모:
- main_instruction.prompt.md가 변경되면 본 파일과 설계서의 매핑 섹션도 함께 갱신한다.
