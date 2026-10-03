# P1 진단 후보 지문 보존 및 교정 연결

- 대상: #585. O1 진단 준비가 묶음 후보를 복사한 뒤 검수용 후보의 `source_refs`만 바꾸어, 동일 후보의 지문이 달라지고 실제 교정 대상에서 제외되는 문제.
- 변경: 새 준비 도구 `scripts/prepare_knowledge_p1_diagnostic.py`에서 참조 재작성 제거. 원본 후보·근거와 묶음 소속 유지. 현재 호출의 원문 핸들은 기존 `segments.bind`에서 별도로 생성.
- 과거 O1/N3 자료·DB·준비본·실행 기록은 변경하지 않음. 새 산출물은 `data/knowledge/semantic_p1_preflight_20261003/`에만 저장.
- 검증: 실제 GenerationService 호출 경계에서 입력을 포착하되 HTTP 생성 호출은 0회. D-1/D-2 각각 기존 입력문과 응답 스키마의 저장 바이트가 동일함. 모델 입력의 `compact`가 후보의 `source_refs`를 이미 제외하므로 불필요한 변경이었음.

| 비교 파일 | 동일한 SHA-256 |
|---|---|
| prompt_D-1.txt | 6f11a8f51b846195142527a5459c1f1bc5973a6934cbd8a5e44252d3e5a843e3 |
| schema_D-1.json | 32f4764a5f3305d891b66a4b21bb4930cdb39e4364bd933017b936c7c8037b67 |
| prompt_D-2.txt | 410ea3c39248a00c0ef5cf51c62c748e005db994757ef26a4f953376345b4860 |
| schema_D-2.json | 1bff7bdcaaf3f6af03ee22d85797c5821f43e85a74878552b50614d07e959ae1 |

- 집중 회귀: 기존 실제 실행 경로의 모델 대역 검사 2건 통과. Critic 정규화 → 현재 지문 확인 → 오류 후보 1개만 Revision → 실제 before/after 이력 → finish → A3 변환 확인. 정상 후보의 현재 지문과 원래 근거 참조 보존, 유형 교정 직후 종속 관계의 이전 검수 무효화, 새 검수 후 재개 시 추가 호출 없음 확인.
- 검사 명령: `PYTHONPATH=. .venv/bin/python -m pytest app/tests/unit/test_knowledge_discovery_contracts.py -q -k observation_check_without_issue` (프로젝트 Python 3.11.9 사용).
- 한계: 교정 회귀는 모델 대역이며 실제 모델의 오류 발견/정의 품질 개선 증거가 아님. O1의 자유 정의 의미 오류 미탐은 해결되지 않음. 다음은 P2 역할 선언 계약과 새 실험 준비이며, 실제 모델 실행은 별도 실행 조율 후 수행.
