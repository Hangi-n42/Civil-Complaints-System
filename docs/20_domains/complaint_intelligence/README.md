# Complaint Intelligence 도메인

- 문서 상태: canonical
- 최종 확인일: 2026-06-21
- 기준 코드:
  - `app/complaint_intelligence/service.py`
  - `app/complaint_intelligence/schemas.py`
  - `app/complaint_intelligence/issue_detection/engine.py`
  - `app/complaint_intelligence/public_insights/`
  - `app/complaint_intelligence/duplicate_merger/`
- 관련 문서:
  - `docs/10_contracts/api/current_api_contract.md`
  - `docs/10_contracts/data/current_data_contract.md`
  - `docs/30_manuals/complaint_intelligence_demo_replay.md`

## 역할

Complaint Intelligence는 메인 RAG/QA 파이프라인을 대체하지 않는 관제형 sidecar입니다. 입력 민원 이벤트를 분석해 저장 가능한 read-model을 만들고, FE Intelligence dashboard는 그 read-model을 조회합니다.

## 구성

- IssueAlert: 급증, 핫스팟, 운영 backlog, 재민원, UX/accessibility 패턴 감지
- PublicAgencyInsight: EvidencePack 기반 공공기관 행정 조치 인사이트
- Duplicate Merge Recommendation Layer: 유사 민원 그룹 후보와 담당자 action gate
- Repository: in-memory 또는 SQLite 기반 저장/조회
- Scheduler/Collector: 실시간 유입원 연결을 위한 단일 프로세스 기반 구조

## 경계

- Complaint Intelligence는 `/api/v1/search`, `/api/v1/qa`의 답변 생성 요청 경로에 직접 개입하지 않습니다.
- PublicAgencyInsight는 AI 내부 개선이 아니라 행정 조치 제안입니다.
- Duplicate Merge candidate는 실제 민원 상태 변경이 아니라 내부 read-model입니다.
- FE는 LLM을 직접 기다리지 않고 저장된 read-model을 조회합니다.

## 읽는 순서

1. `issue_detection_policy.md`
2. `public_insight_policy.md`
3. `duplicate_merge_policy.md`
4. `pii_safety_policy.md`
