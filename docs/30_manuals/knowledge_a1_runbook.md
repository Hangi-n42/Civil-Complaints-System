# A1 탐색 입력 고정과 원문 근거 연결

- 대상: [#520](https://github.com/Hangi-n42/Civil-Complaints-System/issues/520), [설계 §7.1·A1](../05_plans/company_knowledge/autonomous_ontology_plan.md).
- 구현 범위: 입력 준비와 실행에 고정된 원문 조회. `stage=input_grounding`, `status=succeeded`는 입력 준비 완료이며 온톨로지 생성 완료를 뜻하지 않음.
- 기존 SQLite의 sources/versions/runs/blocks/evidence와 직렬 executor 사용. 새 DB 구조·큐·의존성·LLM 호출 없음.

## 저장과 재사용

- `frozen_input`: bundle ID, manifest 전체 바이트의 SHA-256, 선택 scope/step, 선택 파일 메타데이터·해시·파서 버전·옵션·서버 source/version ID 저장.
- 실행 요청을 반환하기 전에 선택 원본을 해시 검증하여 기존 등록 경로의 raw 보관소에 저장. 이후 입력 경로의 파일이나 manifest가 바뀌어도 해당 실행에 반영하지 않음.
- 파일별 discovery unit에 완료된 `parse_run_id`, 순서가 고정된 `block_ids` 저장. 배열 위치 기반 `file_id`와 `block_index`는 실행 안의 조회 위치이며 장기 근거 ID가 아님.
- 등록·수입은 별도 `kind=parse` 실행으로 처리. 각 블록의 서버 ID를 기존 `evidence_id`로 사용하고 evidence 원장에도 원문 구간 저장.
- 동일 source version·파서 버전·옵션의 완료 결과는 ID까지 재사용. 같은 바이트의 다른 출처 사본은 파싱 내용을 재사용하되 source/version/block/evidence ID를 분리하여 출처를 합치지 않음.
- 다른 파서 버전·옵션은 같은 source version에 새 parse 실행 생성. 실패·취소는 기존 성공 `latest_parse_run_id`를 교체하지 않음. 성공 결과가 없는 수동 파싱의 부분 블록은 `latest_parse_attempt_run_id`로 계속 조회 가능.
- TXT/MD는 줄·문자 구간·제목·표 헤더 보존. CSV는 인코딩과 선택 코드 옵션을 저장하고 파일당 한 번 파싱하여 행별 블록 저장. PDF/HTML/HWPX는 기존 위치 보존 어댑터 재사용.
- CSV 어댑터 버전은 2. 이전 행 단위 CSV 실행의 저장 블록은 유지하지만, 실패한 구버전 파서를 새 버전으로 재개하지 않음. 새 parse 실행 필요.

## API 사용 순서

기존 `KNOWLEDGE_ENABLED`와 응답 봉투 유지. 기본 prefix는 `/api/v1/knowledge`.

1. `GET /discovery/sources?scope=current_discovery`로 현재 확정 목록과 `manifest_sha256` 확인.
2. `POST /runs`에 목록의 bundle ID와 hash 전달. `file_ids` 생략 시 해당 scope/step 전체, 지정 시 그 안의 선택 파일만 고정.

```json
{
  "kind": "discovery",
  "bundle_id": "lh_autonomous_input_v1_20260930",
  "manifest_hash": "GET /discovery/sources의 manifest_sha256 값",
  "scope": "current_discovery",
  "step": 0,
  "file_ids": ["lh_15057999:0", "public_housing_act_art2:0"]
}
```

3. `GET /runs/{run_id}`에서 파일별 성공·실패 확인. 시작과 재개에서 임의 manifest 경로·원문 경로·기존 온톨로지 입력을 받지 않음.
4. 아래 실행 바인딩 경로로 조회. `scope/step`을 함께 보내면 고정값과 일치해야 하며, 미지정 시 실행의 고정값 사용.

| 요청 | 반환·경계 |
|---|---|
| `GET /discovery/sources?run_id=…` | 선택 파일과 server source/version ID, 파일별 parse/block 대응 |
| `GET /discovery/read?run_id=…&file_id=…&offset=0&limit=20` | 저장된 원문, locator, source/version/parse/unit/block/evidence ID, 다음 offset |
| `GET /discovery/search?run_id=…&q=…&limit=20` | 같은 고정 블록의 키워드 검색 결과와 미완료 파일 ID |
| `GET /evidence/{evidence_id}` | 기존 사람 검수 경로의 동일 블록·원문 위치·자료 버전 |
| `GET /sources/{source_id}/versions/{version_id}/raw` | 등록 때 보존한 원본 바이트 |

- 역사 단계는 manifest의 initial과 해당 step까지의 updates만 선택. 현재·대비·미래 단계·보류 자료를 함께 반환하지 않음.
- read/search는 manifest·원본 파일·최신 parse 포인터를 다시 읽어 결과를 만들지 않으며, 파싱 상태를 쓰지 않음. 기존 K5 사용 중단/재검토 상태는 조회 시 적용.
- `run_id` 없는 기존 개발용 read/search는 유지하며 파일을 직접 파싱함. **A2 실행기는 반드시 run_id를 전달**해야 함.
- A1 검색은 저장 블록의 제한된 키워드 순회. BM25 순위·자료군 균형·탐색 큐는 A2 범위.

## 취소·재개

- `POST /runs/{run_id}/cancel`: 현재 파일의 parse 처리가 끝난 뒤 다음 파일 중단. 큰 파일 안에서 즉시 중단하는 기능은 아님.
- `POST /runs`에 `{"kind":"discovery","retry_of_run_id":"…"}` 전달. 미완료 실행은 새 run ID로 재개하며 원래 실행과 고정 입력을 보존. 성공 파일의 parse/block ID는 재사용.
- 이미 성공한 입력 준비 실행의 재개 요청은 기존 run ID 반환. 원본·manifest를 다시 읽지 않음.
- 프로세스 재시작은 미완료 실행을 실패로 표시. child parse 저장 뒤 discovery 대응 저장 전에 중단된 경우에도 동일 recipe의 완료 parse를 찾아 재사용.
- 파일 일부 단위만 실패한 경우 기존 parse 재시도 경로로 실패 단위만 처리하며 성공한 단위의 근거 ID 유지.
- 고정 파서가 바뀌었고 재사용할 완료 결과가 없는 파일은 실패 사유를 남김. 새 recipe를 기존 실행에 조용히 섞지 않고 새 입력 실행으로 처리.
- 새 선택 범위·manifest·파일 내용은 새 실행으로 시작. 재개 요청에 다른 선택값을 함께 보내면 거절.

## 확인 결과 — 2026-09-30

- 환경: macOS, Python 3.11.9. 관련 단위/API 회귀에서 범위 격리, manifest 변경·파일 순서 변경, 파서 변경, 다른 출처의 동일 파일, 취소·재개·재시작, 포인터 분리, 사용 중단, 기존 K3/K4/K5/K6 연결 확인.
- 관련 테스트 71개 통과, 1개 skip. `git diff --check` 통과. 실행 명령:

```sh
python -m pytest app/tests/unit/test_knowledge_discovery_inputs.py app/tests/unit/test_knowledge_discovery_run.py app/tests/unit/test_knowledge_service.py app/tests/unit/test_knowledge_parsers.py app/tests/unit/test_knowledge_api.py app/tests/unit/test_knowledge_ontology_run.py app/tests/unit/test_knowledge_extraction_run.py app/tests/unit/test_knowledge_extraction_store.py app/tests/unit/test_knowledge_snapshots.py app/tests/unit/test_knowledge_search.py -q
```

- 새 CSV 합성 fixture는 CP949·다중 행 셀·행 위치·단일 순회 확인. HTML 표와 HWPX 문단은 합성 fixture로 확인.
- 허용 LH 원본은 별도 검증용 로컬 원장에 등록. 운영 원장·기존 pilot·manifest 수정 없음.

| 실행 범위·선택 파일 | 저장 블록 |
|---|---:|
| current: `lh_15057999:0` (MD 업무 명세) | 66 |
| current: `public_housing_act_art2:0` (TXT 조문) | 3 |
| current: `rule_annex4_20260824:0` (PDF 13쪽) | 417 |
| contrast: `lh_15139855:0` (CP949 CSV, 별도 실행) | 576 |

- 실제 확인: 등록·고정 → 취소·재개 → read/search → 동일 입력 재사용·원본/근거 재조회 통과. 취소 시점에는 현재 묶음의 3파일이 완료되어 있었고 재개 시 그 결과를 재사용. 미완료 파일의 재개는 합성 fixture에서 별도 확인.
- 파일별 앞 2블록의 read/evidence 텍스트·locator 일치, raw SHA-256 일치 확인. 현재 검색 14건, 대비 검색 상한 20건 반환. 범위 밖 파일 404, 다른 scope 요청 422 확인.
- 파서 호출 총 16회(MD 1, TXT 1, PDF 페이지 13, CSV 1). 읽기·검색·동일 입력 재사용에서 추가 호출 0회. LLM 호출 0회.
- 확인한 manifest hash: `eb1379a48588ba7bf6c2be3dc109a797f9da1740ac5599aca85b33bdea315cdf`.
- 로컬 증적: `data/knowledge/a1_smoke_20260930/result.json` 및 같은 폴더의 검증 DB. 원본·DB·증적 JSON은 Git에 포함하지 않음.
- 원본 전체의 의미·표 정확성 전수 검수, 전체 19파일 실행, Windows 실기, LLM 품질·사람 검수 효과는 미검증. 기존 pilot 원본을 요구하는 테스트 1개는 격리 worktree에 그 원본이 없어 skip.

## A2 연결부와 후속 범위

- `RunRequest(kind='discovery', …)`와 `discovery_run.catalog/read/search(service, run_id, …)`를 탐색기의 입력 계약으로 사용.
- 완료된 discovery unit의 parse/block/evidence 참조로 구조 프로파일·frontier·역할별 분석을 추가. source version의 최신 포인터를 다시 따라가지 않음.
- [A2](https://github.com/Hangi-n42/Civil-Complaints-System/issues/521): 자료 프로파일·검색 순위·탐색 선택·LLM 역할·예산. A3~A6: 변경 모델·검수 화면·승인/소비자·실제 효과 확인.
- 현재 사용자 결정이 필요한 사항 없음.
