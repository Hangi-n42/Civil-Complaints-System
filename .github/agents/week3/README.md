# Week3 Multi-Agent Prompt Pack

이 디렉토리는 Week3(M2) 운영을 위한 역할 분리형 에이전트 프롬프트 모음입니다.

## 파일 구성
- orchestrator.prompt.md: 작업 분해/우선순위/핸드오프 총괄
- be1_data_structuring.prompt.md: 데이터/구조화/정제/평가셋
- be2_retrieval.prompt.md: 임베딩/인덱싱/검색/필터/검색지표
- be3_generation_api.prompt.md: API/RAG/파싱/성능/모델 벤치마크
- fe_demo_ui.prompt.md: Streamlit UI/데모 UX/가시화
- reviewer_qa_gate.prompt.md: 계약/KPI/Gate 관문 리뷰

## 권장 협업 플로우
1. orchestrator가 목표, 제약, 완료조건을 선언한다.
2. 역할별 에이전트가 작업안과 리스크를 제출한다.
3. reviewer가 계약 위반, KPI 리스크, 누락 테스트를 지적한다.
4. orchestrator가 피드백을 반영해 실행계획을 확정한다.
5. 구현 완료 후 reviewer가 Gate 통과 여부를 판단한다.

## 공통 출력 규칙
- 첫 줄: 요청 분류 (기획/설계/구현/실험/디버깅/발표 준비)
- 둘째 줄: 현재 우선순위 1줄
- 그 다음: 판단 요약, 근거, 실행 작업, 산출물, 리스크/대안
