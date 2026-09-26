# 회사 지식 K2 구현 결과·실행 안내

- 기준일: 2026-09-26
- 상태: K2 구현 및 Mac 로컬 확인 완료. P0 전체·Windows 실행·지식 품질 검증 완료를 뜻하지 않는다.
- 기준: [마일스톤](../05_plans/company_knowledge/milestones.md), [최소 계약](../05_plans/company_knowledge/contracts.md).

## 구현 선택과 범위

자료 등록 → 원문 보존 → 형식별 추출 → 원문 위치 조회 순서로 구현했다. 파서 담당·백엔드 담당·독립 리뷰 에이전트로 일을 나누고 UI와 실제 통합 확인을 연결했다. Ponytail 원칙에 따라 이미 선정한 패키지의 공개 API와 SQLite·표준 라이브러리를 사용했다. 별도 큐 서버·캐시·플러그인 프레임워크·LLM 호출은 추가하지 않았다.

- `app/knowledge/parsers.py`: CSV는 표준 csv, HTML은 BeautifulSoup, PDF는 pdfplumber, HWPX는 python-hwpx의 TextExtractor/ParagraphInfo를 직접 호출한다. HWPX의 원본 XML 경로·셀 위치는 ZIP/XML로 보완한다. 패키지 내부를 수정하거나 코드를 복사하지 않았다.
- `repository.py`, `service.py`, `schemas.py`: SQLite 출처·버전·추출 블록·근거·작업 원장. 출처/해시 중복 등록 방지, 원문 보존, 새 파싱 이력, 단위별 저장, 취소·실패 단위 재시도, 서버 재시작 후 중단 작업 표시.
- `app/api/routers/knowledge.py`: `/api/v1/knowledge` 아래 별도 API. 기존 Search/QA 응답 계약을 변경하지 않는다.
- `frontend/app/knowledge/page.tsx`: 자료/후속 버전 등록, 날짜·권리·해시·상태, 추출·취소·재시도, 원본 다운로드와 근거 위치 조회.
- `scripts/import_knowledge_pilot.py`: 고정된 로컬 원문 11개를 해시 확인 후 API로 등록·추출. 평가 정답은 입력하지 않는다.

재추출해도 이전 근거 ID를 삭제하지 않는다. 기본 블록 조회는 최신 전체 파싱과 그 재시도 계열의 성공 단위를 보여준다. 재시도 시 파서 버전·옵션이 달라지면 새 전체 파싱을 요구한다. 단일 프로세스·직렬 작업을 전제로 하며 uvicorn 다중 worker로 실행하지 않는다.

## 실제 확인 결과

| 확인 | 결과 |
|---|---|
| 선정 원문 API 등록·파싱 | 11개 입력, 80개 처리 단위 성공, 실패 0, 블록 3,047개 |
| 원본 다운로드 | 11개 모두 등록 SHA-256과 일치 |
| 근거 조회 | 각 입력 첫 근거의 발췌/문자 범위와 저장 블록 일치 |
| 위치·내용 표본 | CSV 단지/행, HTML 표·명시적 단지 설명, PDF 페이지/2면/표·셀, HWPX 구역/문단·표 위치 확인 |
| 관련 Python 테스트 | 6 passed (6.18초). 중복·실패·재시도·취소·재시작·API·실제 포맷 표본 포함 |
| 프런트엔드 | TypeScript 및 변경 화면/사이드바 ESLint 통과. 실제 브라우저 자료 목록·CSV 근거 조회 확인. 화면에서 재추출 시작 후 API로 6/6 성공 확인 |
| 의존성 | pip check 통과. Streamlit Home 초기 렌더 예외 없음 |

최초 통합 run ID: `b8f0784faf9d47a79a366116a0dc4f3f`. 상세 실행 기록은 로컬 `data/knowledge/pilot_v1/k2_import_result.json`에 있다. 파싱 완료 수는 의미 정확도나 평가 과제 성공률이 아니다. `alignment_status=matched`는 현재 전체 블록 발췌가 저장 텍스트와 일치한다는 뜻이며 주장 검증·사람 승인과 다르다.

독립 리뷰에서 취소 응답 처리, HWPX 범위 메타데이터, 자료 전환 시 작업 표시, 지원 확장자 및 비동기 자료 전환 문제를 수정했다. HTML A5의 985/521/464 설명은 DOM alt가 아닌 명시적 단지 데이터 문자열에 있으므로 단지 코드와 해당 설명 필드만 추출하며 스크립트를 실행하지 않는다.

## 실행

Python 3.11.9 가상환경을 활성화한다. Mac에서는 `source .venv/bin/activate`, Windows PowerShell에서는 `.venv\Scripts\Activate.ps1`을 사용한다. 프로젝트 루트에서 필요한 의존성을 설치한다.

```sh
python -m pip install -r requirements.txt
```

K2에서 실제 사용한 버전은 pdfplumber 0.11.10, python-hwpx 6.5.0, BeautifulSoup4 4.15.0, python-multipart 0.0.32이다. pdfplumber의 Pillow>=12.2 요구와 기존 Streamlit의 Pillow<12 제약이 충돌해 Pillow 12.3.0·Streamlit 1.64.0으로 함께 조정했다. 현재 Mac 가상환경에서 설치·pip check·초기 UI를 확인했으며 깨끗한 Windows 환경 전체 설치는 미확인이다.

로컬 `.env`:

```dotenv
KNOWLEDGE_ENABLED=true
KNOWLEDGE_DB_PATH=data/knowledge/knowledge.db
```

공통 기본값은 기능 OFF이며 DB 상대 경로는 프로젝트 루트를 기준으로 한다. 현재 로컬 `.env`에서는 ON이다. 원문은 DB 디렉터리 아래 `raw/`에 보존한다. API는 단일 프로세스로 실행한다.

```sh
python -m uvicorn app.api.main:app --host 127.0.0.1 --port 8001
python scripts/import_knowledge_pilot.py --api-base-url http://127.0.0.1:8001
```

가져오기 명령은 `data/knowledge/pilot_v1/raw/`에 고정 원문이 있을 때만 사용한다. 이미 등록된 파일은 중복 생성하지 않지만 새 파싱 작업은 수행한다. 현재 로컬 DB에는 이미 등록·추출되어 있으므로 다시 실행할 필요가 없다.

프런트엔드 `frontend/.env.local`의 `NEXT_PUBLIC_API_BASE_URL`을 `http://127.0.0.1:8001`로 설정한 뒤 `frontend/`에서 실행한다.

```sh
npx next dev --webpack --hostname 127.0.0.1 --port 3000
```

`http://127.0.0.1:3000/knowledge`에서 자료 → 추출 구간 → 원문 위치를 확인한다. 이번 확인 서버는 기존 민원 인텔리전스 스케줄러를 끄고 실행했다. 일반 개발 시 해당 기존 설정은 별도로 선택한다.

## 한계와 다음 작업

- OCR·스캔 PDF, 모든 PDF/HWPX 레이아웃, 대용량 전체 CSV 성능은 검증하지 않았다. 선정 자료 범위를 우선 지원한다.
- HTML의 단지 스크립트 메타데이터 및 HWPX 임대주택 Q1~Q16 범위는 선정 원문의 구조에 맞춘 제한된 어댑터다. 일반 문서는 일반 본문/전체 구역 추출을 사용한다.
- Windows 실행, 12개 평가 과제, 사람 검토 시간·B0/B1/B2 효용, 기관 운영 권리 확인은 미완료다. 원문 권리 미확인을 사용 허용으로 바꾸지 않았다.
- 다음은 K3: 이 블록과 근거를 입력으로 LinkML 온톨로지 후보, OntoGPT/AutoSchemaKG의 선정 자산, 기존 Ollama 호출을 연결한다. K2에서 지식그래프나 온톨로지를 생성했다고 표시하지 않는다.
- K2 완료에 사용자 추가 결정은 없다. 기존 변경과 고정 평가 입력은 보존했으며 커밋·푸시는 하지 않았다.
