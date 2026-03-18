# Title
[Week 1][BE2][민건] 임베딩·벡터DB 후보 비교 및 Ollama/RAG API 입력 구조 초안 작성

# Suggested Labels
- backend
- be2
- week1
- retrieval
- rag

# Suggested Assignee
- 민건

# Summary
BE2의 1주차 핵심 목표는 검색과 생성 파이프라인의 기술 기준선을 세우는 것이다.  
즉, 어떤 임베딩 모델과 벡터DB를 우선 선택할지, Ollama 기반 RAG API를 어떤 입출력 구조로 연결할지를 결정해야 한다.

# Source Docs
- [docs/be2_manual.md](../../be2_manual.md)
- [docs/api_spec.md](../../api_spec.md)
- [docs/schema_contract.md](../../schema_contract.md)
- [docs/prd_draft.md](../../prd_draft.md)

# Tasks
- [ ] 임베딩 후보 모델 비교 계획 수립 (`BGE-m3`, `KoSimCSE` 등)
- [ ] ChromaDB와 FAISS의 장단점 비교 메모 작성
- [ ] 1차 벡터DB 우선 선택안 제시
- [ ] 검색용 메타데이터 키 정의 (`category`, `region`, `created_at`, `entity_labels` 등)
- [ ] 청크 메타데이터 구조 초안 작성
- [ ] Ollama 로컬 실행/연동 가능 여부 확인
- [ ] RAG API 입력/출력 초안 작성
- [ ] `/search`와 `/qa` 응답 형식에서 FE가 필요한 필드 확인
- [ ] BE1 구조화 결과와 인덱싱 연결 포인트 정리
- [ ] BE3와 QA 응답 파싱 안정화 관점에서 필수 필드 협의

# Deliverables
- 임베딩 비교 계획 문서
- 벡터DB 비교 메모
- 검색 메타데이터 구조 초안
- 청크 구조 초안
- Ollama 연동 확인 메모
- RAG API 입력/출력 초안

# Acceptance Criteria
- 팀이 1차 임베딩 모델과 벡터DB 선택 방향을 이해한다.
- 검색과 QA의 연결 구조가 문서로 설명 가능하다.
- 2주차 PoC에서 바로 검색/QA 실험을 시작할 수 있다.

# Collaboration
- BE1: 구조화 결과 중 검색용 필드를 어떻게 넘길지 협의
- FE: 검색 카드/챗 응답에 꼭 필요한 응답 필드 정리 필요
- BE3: JSON 파싱과 citation 정합성에 필요한 QA 응답 구조 협의

# Notes
이슈 목표는 완성 구현이 아니라, 2주차 PoC를 막지 않는 기술 선택과 인터페이스 초안을 만드는 것이다.
