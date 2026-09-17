# 폴더별 기능 보존 정리 기록

2026-09-17. 기준 커밋 `b53134a`. 직전 작업의 정리 내용을 보존하고 이어서 점검했다.
파일 목록과 Python/TypeScript 함수 중복 후보를 폴더별로 순회한 뒤, 변경할 함수의 구현과 호출부를 확인했다.
모든 줄에 대한 정밀 코드 리뷰나 전체 서비스의 실운영 검증을 의미하지 않는다.

## 폴더별 결과

| 폴더 | 결과 |
| --- | --- |
| `app/core` | 설정·예외·로그·제목 생성 유지. 정리만으로 동작 보존을 확실히 설명할 추가 변경 없음 |
| `app/api` 및 `routers`, `schemas` | 오류 응답·라우터·스키마 계약 유지 |
| `app/ingestion` 및 `loaders`, `preprocess` | 입수·전처리·PII 처리 유지. 빈 패키지도 호환성을 위해 보존 |
| `app/structuring` 및 하위 폴더 | 규칙/LLM 추출, 검증, 긴급도 유지. 유사한 추출기도 스키마·프롬프트·폴백이 달라 통합하지 않음 |
| `app/retrieval` 및 `vectorstores` | 직전 정리 유지: 동일한 요약문 생성 구현 공유, 기존 메서드 진입점 보존 |
| `app/retrieval/analyzers`, `router`, `search`, `pipeline`, `embeddings` | 검색·분해·라우팅 규칙 유지 |
| `app/generation/normalization` | 응답의 9개 타입 검사 분기를 필드/타입 목록 순회로 정리. 누락 키·오류 정렬 동일 |
| `app/generation`의 나머지 하위 폴더 | 프롬프트·LLM 호출·파싱·인용 및 근거 검증 유지 |
| `app/evaluation` 및 `ares_lite` | 기존 파일 해시 유틸리티를 스크립트에서 재사용. 기본 제한 5/20 등 의미가 다른 정규화 함수는 유지 |
| `app/complaint_intelligence` | 직전 정리 유지: 메모리/SQLite 저장소의 동일한 재귀 마스킹 공유 |
| `app/complaint_intelligence/duplicate_merger`, `issue_detection`, `public_insights` | 점수·확인/거절 상태·감지 임계값·품질 검증 유지 |
| `app/ui`, `components`, `services`, `pages` | 직전 날짜·근거 표시 공유 유지. 두 유사 민원 렌더러의 상태·HTML 이스케이프 중복 통합. 따옴표 처리까지 기존 동작 유지 |
| `src/pii` | 탐지와 추가 마스킹에서 동일한 주소 정규식 2개 공유. 패턴·플래그·검사 순서 동일 |
| `src/structuring/pii` | 실패 시 차단 정책 및 위험 판정 유지 |
| `frontend/lib` | API와 초안 화면의 요청 항목 정규화·상세 항목 선택을 기존 함수로 통합 |
| `frontend/app`, `components`, `scripts` | 화면·상태 전이·데모 준비 동작 유지. 추가 동일 함수 중복 후보 없음 |
| `scripts` | 평가셋 생성기의 SHA-256 중복을 기존 평가 유틸리티로 교체. CLI 이름·옵션 유지 |
| `app/tests`, `frontend/__tests__`, `scripts/test_*`, `tests` | 기존 테스트·픽스처 보존. 변경된 표시/형식 검사에 작은 회귀 테스트 추가 |
| `configs`, `schemas`, `.github`, 루트 실행 설정 | 설정·계약·실행/배포 진입점 보존 |
| `docs`, `data`, `reports`, `logs` | 이 기록 외에 기존 문서·데이터·PPT·실행 산출물은 수정/삭제하지 않음 |

과거 벤치마크 스크립트에는 여전히 중복이 있다. 운영 코드와 confidence 기본값이
다르거나 실험별 설정·프롬프트에 의존하므로 공통화하지 않았다.
이 작업은 폴더 삭제, 새 의존성, 새 추상화 계층, 프롬프트 변경을 포함하지 않는다.

## 확인 결과

- 변경 후 관련 Python 테스트 82개 통과(49개 + 33개), 프런트엔드 테스트 42개 통과.
- 프런트엔드 TypeScript 검사 통과. Python 405개 파일 구문 검사 통과.
- 이번 추가 비교 215건 통과: 기존 HTML 전체 출력, 응답 오류 목록, PII 패턴/플래그/순서, 파일 해시 경계값.
- 직전 정리에서 기존 커밋과 728개 입력 조합의 반환값 일치를 확인했다.
- 평가셋 생성기 `--help` 실행 및 `git diff --check` 통과.
- 변경 전에도 있었던 sklearn 경고 3개 유지: 저장 모델 1.7.2와 설치 버전 1.8.0 불일치.
- 전체 테스트·실제 LLM 재평가·브라우저 E2E·Windows 실행은 이번 정리에서 수행하지 않았다.
  확인 범위에서 기능 차이는 발견되지 않았으나 전체 기능에 대한 무결점 보장은 아니다.
- 커밋·푸시하지 않음. 기존 로컬 PPT 파일 및 다른 작업 상태 보존.
