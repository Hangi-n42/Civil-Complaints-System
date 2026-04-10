# 개발 기술 스택 가이드 (Adaptive RAG + Workbench)

문서 버전: v2.0  
최신화: 2026-04-09

## 1. 문서 목적

본 문서는 Week5-8 기준의 확정 기술 스택을 정의한다. 목표는 Adaptive RAG 코어 로직과 데모 워크벤치 구현을 빠르게 통합하는 것이다.

## 2. 아키텍처 스택

- Backend API: FastAPI, Uvicorn, Pydantic
- Frontend: React/Next.js
- Retrieval: ChromaDB, sentence-transformers
- Generation: Ollama, PromptFactory
- Config/Infra: python-dotenv, pyyaml

## 3. 레이어별 책임

### 3.1 Backend (FastAPI)
- `/search`, `/qa`를 중심으로 adaptive 필드 전달
- `routing_trace`, `routing_hint`, `structured_output` 계약 유지

### 3.2 Frontend (React/Next.js)
- 3단 Workbench 레이아웃 구현
- 좌: 네비게이션
- 중: 실시간 민원 목록/상태
- 우: AI 패널(요약, 유사 민원, 답변 초안, citation, 편집)

### 3.3 Adaptive Core
- Analyzer: Length/Topic/Multi
- Router: route key 기반 전략 선택
- Generation: topic-aware prompt + normalize_response

## 4. 구현 우선순위

1. API 계약 필드 고정
2. Adaptive core 모듈 연결
3. Next.js Workbench 렌더
4. E2E 데모 시나리오 동결

## 5. 운영 메모

- Week5-8은 스택 전환 이후 기능 통합에 집중한다.
- 추가 지표 벤치마크나 리팩토링 중심 작업은 범위에서 제외한다.
