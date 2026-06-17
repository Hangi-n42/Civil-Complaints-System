# responsible_unit 도출기 (BE1 고도화 #3)

민원 텍스트 → 처리 책임 부서 후보(`responsible_unit`)를 도출한다.
설계 합의: **벡터 검색 핵심 + LLM 선택 레이어 / 과·담당관 leaf 우선 / 부서명 환각 0**.

## 산출물

| 파일 | 역할 |
| --- | --- |
| `scripts/build_department_master.py` | 1단계 필터링. `busan_departments_tasks.json` → `busan_departments_master.json` |
| `busan_departments_master.json` | 배정용 정제 부서/업무 (116부서 / 1,998업무) |
| `busan_departments_master.stats.json` | 필터링 통계·제외 내역(검토용) |
| `app/structuring/department_assigner.py` | 2~4단계. 임베딩·검색·집계·LLM 재랭킹 |
| `app/structuring/enrichment.py` | 요청 #1 entity_texts · #2 legal_refs(도메인) · #5 key_terms + 시설 사전 |
| `app/structuring/legal_dictionary.py` | #2 Phase A — 법령명/약칭/부산조례 사전 매칭 + 도메인 병합 |
| `scripts/build_law_dictionary.py` | 법제처 API 로 law_dictionary.json/busan_ordinances.json 생성(로컬) |
| `docs/60_specs/legal_corpus_phase_b.md` | #2 Phase B — 조문 단위 본문 코퍼스+검색 설계서 |
| `app/tests/unit/test_legal_dictionary.py` | 사전 매칭/병합 순수 로직 테스트 (6) |
| `app/structuring/service.py` | BE1 통합 (3개 필드 추가, 시설 키워드 확장) |
| `app/core/config.py` | `ENABLE_RESPONSIBLE_UNIT` / `RESPONSIBLE_UNIT_USE_LLM` 플래그 |
| `app/tests/unit/test_department_assigner.py` | responsible_unit 순수 로직 테스트 (10) |
| `app/tests/unit/test_enrichment.py` | entity_texts/legal_refs/key_terms 순수 로직 테스트 |

## 1단계 — 필터링 (결정적, 모델 불필요)

원본 150부서/3,368업무에서 노이즈를 제거해 검색 신호를 선명하게 한다.

- **Layer A 부서 블랙리스트**: 보좌·홍보, 감사·청렴, 기획조정실 내부(기획/예산/법무/세정/회계), 행정자치국 살림(총무·인사·정보화), 자치경찰위 내부행정, 소방 내부행정, 직책 placeholder 등 34개 제외.
- **Layer B 업무 보일러플레이트 제거(핵심)**: 거의 모든 부서에 반복되는 내부 행정 업무(업무 총괄, 주요 업무계획, 조직·인사, 성과관리, 국정감사, 법제심사, 서무·보안·청렴·기록물, 회계·지출·물품, 청사 관리, 예산 결산, 국급여·연말정산, 국장 운전·차량, 국회/시의회, 포상·공적심사 등) 781개 제거. 복지 도메인의 '급여/수당' 등은 anchored 패턴으로 보존.
- **Layer C leaf 우선**: 정제 후 실질 업무가 2개 미만으로 남는 부서(순수 국/실 롤업, placeholder)는 제외. 예: `교통혁신국`·`교통혁신과`는 보유 업무가 전부 내부행정이라 제외되고, 실제 처리 단위인 `대중교통과`·`택시운수과`가 남는다.

```bash
python scripts/build_department_master.py
```

> 주의: 블랙리스트는 명시적·검토 가능하게 작성했다. 누락/오제외 의심 부서는 `busan_departments_master.stats.json`의 `dropped_detail`로 확인 후 스크립트 상수만 수정하면 된다.

## 2~4단계 — DepartmentAssigner

```
민원 질의 ──embed(bge-m3)──▶ Chroma(busan_departments_v1) Top-K 업무 검색
        └ task 히트를 '부서'로 집계 → confidence + evidence
        └ (선택) LLM 재랭킹: 후보 집합 안에서만 선택, 사후검증으로 환각 폐기
```

- **부서명 환각 0**: 후보는 항상 컬렉션(=마스터 JSON)에 실재하는 정확한 부산시청 부서명에서만 나온다. LLM을 켜도 `validate_llm_units()`가 후보 밖 이름을 폐기한다.
- **집계 규칙(휴리스틱)**: `confidence = min(0.99, 최고유사도 + 0.02 × (추가 히트 수, 최대 5))`. 같은 부서가 여러 업무로 매칭될수록 소폭 가산.
- **evidence**: 가장 유사한 업무 문구 + 질의와 겹치는 핵심어.

### 출력 예시 (스키마)

```json
{
  "responsible_unit": [
    {"name": "도로안전과", "confidence": 0.83, "evidence": ["포트홀 보수 도로 파손 정비", "포트홀", "도로"], "source": "be1_structured"},
    {"name": "대중교통과", "confidence": 0.40, "evidence": ["시내버스 노선 조정"], "source": "be1_structured"}
  ]
}
```

> ⚠️ **confidence는 코사인 유사도에서 유도한 미보정(uncalibrated) 점수**다. 민원→부서 정답셋이 없어 검증된 확률이 아니다. BE2는 절대 임계값이 아니라 **상대 순위·상대 강도**로만 사용할 것. 정답셋 확보 전까지 정확도(P@1 등) 수치는 산출 불가.
> 출처 계약: 실제 BE1 담당부서 후보는 `source: "be1_structured"`를 포함한다. 후보가 없으면 `responsible_unit: []`를 반환한다. category/source 기반 fallback을 별도로 생성하는 경로는 `source: "category_source_fallback"`로 구분하고, BE2 저장 metadata에는 `responsible_units_source`로 보존한다.

## 로컬 실행 가이드 (인덱스 빌드·검색)

이 단계는 bge-m3(~2.3GB)·chromadb·(선택)Ollama가 필요해 **로컬 환경에서** 수행한다.

```bash
pip install chromadb sentence-transformers   # 미설치 시
# 환경변수(미설정 시 기본값): EMBEDDING_MODEL=BAAI/bge-m3, EMBEDDING_DEVICE=cpu, CHROMA_DB_PATH=data/chroma_db
python - <<'PY'
from app.structuring.department_assigner import get_department_assigner
a = get_department_assigner()
print(a.build_index(rebuild=True))            # 1회 적재 (1,998 업무)
print(a.assign("연산교차로 포트홀로 도로가 깊게 파였습니다 보수 요청", use_llm=False))
PY
```

- `use_llm=True`로 켜면 Ollama(`OLLAMA_BASE_URL`, `OLLAMA_MODEL`)로 후보 재랭킹. **Ollama 미가동 시 자동으로 벡터 결과로 폴백**한다.

## BE1 통합 (적용됨)

`app/structuring/service.py` 의 `structure()` 에 다음 검색 보조 필드를 추가했다(규칙 #6: 추론 항목 confidence + evidence 포함).

```python
candidate["entity_texts"]     = normalize_entity_texts(entities, text)          # 요청 #1
candidate["legal_refs"]       = classify_legal_refs(text)                        # 요청 #2
candidate["key_terms"]        = build_key_terms(text, entity_texts, legal_refs)  # 요청 #5
candidate["responsible_unit"] = self._assign_responsible_unit(text, entity_texts, key_terms) # 요청 #3
```

`_assign_responsible_unit()` 는 `ENABLE_RESPONSIBLE_UNIT` 플래그가 꺼져 있거나(기본값) 임베딩 인덱스/모델이 미가용이면 **빈 리스트로 안전 폴백**한다 → 기존 파이프라인·테스트에 영향 없음.

### 활성화 절차

```bash
# 1) 인덱스 1회 빌드 (로컬, bge-m3/chromadb 필요)
python -c "from app.structuring.department_assigner import get_department_assigner as g; print(g().build_index(rebuild=True))"
# 2) 플래그 on (선택: LLM 재랭킹도 on)
export ENABLE_RESPONSIBLE_UNIT=true
export RESPONSIBLE_UNIT_USE_LLM=false
```

> `ENABLE_RESPONSIBLE_UNIT=true` 인데 인덱스가 비어 있으면 첫 `structure()` 호출에서 임베딩 모델 로드가 발생한다. 운영에서는 기동 시 `build_index()` 를 1회 선실행할 것.

## 검색 신호 보강 필드 (요청 #1 / #4)

`app/structuring/enrichment.py` (결정적 규칙·사전 기반, 모델 불필요).

### entity_texts (요청 #1) + 시설 체크리스트 고도화

- `_facility_keywords` 를 기존 8개 → **83개**로 확장(`FACILITY_KEYWORDS`). 도로/교통·상하수/환경·공원/체육·건축 시설 포함, 저모호성 명사 위주.
- `OBJECT_LEXICON` 135개 표준 객체로 변이를 정규화. 예: `포크레인`→`굴착기`, `3톤 미만 지게차`→`지게차`, `보안등`/`공원등`/`조명등`→`가로등`(evidence 에 원문 span 보존).
- 문화/예약, 노동/고용, 기업/무역/세무, 건설/주택/자동차 도메인의 행정 객체를 보강한다. 예: `공연`, `티켓`, `예매`, `임금체불`, `고용보험`, `정책자금`, `수출입`, `세무신고`, `건설공사`, `분양`, `화물운송`.
- `도로법`·`도로교통법`·`도로관리청`·`도로점용`처럼 법령·기관·제도 인용 문맥의 일반어는 `entity_texts` 오탐에서 제외한다. 실제 대상물 문맥(`도로가 파손`, `보행로 보수`)은 유지한다.
- BE2 readiness 대응 실측: 처리 데이터 3,280건 기준 lexicon-only 커버리지 20.12% → 73.23%, 규칙 NER+lexicon 커버리지 46.37% → 76.98%. `civil_cases_v1` 9,132건 기준 현재 metadata는 11.03%이나, 개선 로직 적용 예상 커버리지는 74.12%다. 실제 적재율은 BE2 재인덱싱 또는 metadata backfill 이후 다시 측정한다.
- 출력: `[{"text": canonical, "label": "OBJECT"|"FACILITY", "confidence": float, "evidence": [span]}]`. confidence 휴리스틱: canonical 직접 등장 0.9 / 변이 정규화 0.85 / 규칙 NER FACILITY 흡수 0.8.

### legal_refs (요청 #2) — Phase A 고도화 적용

`get_legal_ref_matcher().match(text)` 가 **두 신호를 병합**한다.

- **사전 직접매칭(고신뢰)**: `law_dictionary.json`(법제처 현행법령 목록) / `busan_ordinances.json`(부산 자치법규)이 있으면, 민원에 직접 등장하는 **법령명(0.95)·약칭(0.9)·조례명(0.9)** 을 매칭하고 `law_id`·`source` 를 부여. 약칭 매칭은 정식 법령명을 `name`으로 낸다(예: "개보법"→개인정보 보호법). 커버리지가 18개→현행법령 전체+부산 조례로 확장.
- **도메인 lexicon(보강)**: 법령명이 직접 안 적힌 민원을 위해 18개 핵심 법령의 트리거 어휘 매핑 유지(`source="domain"`). 실재 법령명만 사용(환각 금지).
- 출력: `[{"name", "confidence", "evidence", "law_id", "source"}]`, 상위 4개(name 기준 병합, confidence 최댓값).
- **사전 파일이 없으면 도메인 lexicon 으로 안전 폴백**(하위호환). 사전은 `scripts/build_law_dictionary.py`(법제처 OC 키 필요, 로컬 실행)가 생성.
- `law_id` 는 **Phase B(조문 검색)의 법령 필터로 직결**된다 → `docs/60_specs/legal_corpus_phase_b.md`.

#### Phase A 실측 (크롤 사전 적용 후)

법제처 크롤로 사전을 채운 결과: `law_dictionary.json` **5,585개**(law_id 100%, 약칭 2,519개, dept 5,584, 중복·결측 0), `busan_ordinances.json` **9,086개**(전부 부산, law_id 100%). 2자 법령명(민법·상법·형법)은 오탐 방지로 매칭 제외(`_MIN_NAME_LEN=3`).

before(도메인 18개) → after(실사전) 효과:

| 민원 | before | after |
| --- | --- | --- |
| "…개인정보 보호법 위반 신고" | `[]` | 개인정보 보호법 · 0.95 · name_match |
| "감염병예방법상 자가격리 위반 과태료" | `[]` | 감염병의 예방 및 관리에 관한 법률 · 0.9 · abbr_match |
| "근로기준법 위반 임금 체불 신고" | 근로기준법 · 0.75 · domain | 근로기준법 · 0.95 · name_match |
| "3톤 미만 지게차 면허…" (법령 미언급) | 건설기계관리법 · 0.6 · domain | 건설기계관리법 · 0.6 · domain (유지) |
| "부산광역시 …부설주차장… 조례 거주자우선주차" | 주차장법 · 0.75 · domain | **부산 조례 · 0.9 · ordinance** + 주차장법 · domain |
| "부산광역시 …반려동물… 조례 반려견 등록" | 동물보호법 · 0.75 · domain | **부산 조례 · 0.9 · ordinance** + 동물보호법 · domain |

핵심: 18개 밖 법령은 before가 전부 놓쳤으나(`[]`) after는 법령명·약칭을 0.9~0.95로 매칭하고, **부산 자치법규를 국가법령과 함께** 제시한다. 법령이 직접 안 적힌 민원은 도메인 후보를 유지(오탐 없음).

### 데이터 위치

크롤·정제 산출물은 `data/` 하위로 이동했고 코드가 자동 참조한다.

- `data/laws/law_dictionary.json`, `data/laws/busan_ordinances.json` — `LegalRefMatcher` 기본 경로.
- `data/departments/busan_departments_master.json`(+`.stats`), `data/departments/busan_departments_tasks.json` — `DepartmentAssigner.master_path` / 필터 스크립트 입출력 기본 경로.

> ⚠️ 매칭은 **어휘 동시출현**일 뿐 법적 적용을 단정하지 않는다. 반드시 '후보'로 사용(요청 #2도 후보 제시를 명시).

### key_terms (요청 #5)

- entity_texts(객체) > 행정어 사전(`ADMIN_TERMS`) > legal_refs 근거 순 가중으로 종합 랭킹. 일반어("신청/문의/절차/방법" 등) 배제, 더 긴 표현의 부분문자열 제거, **3~8개** 반환.
- 출력은 BE2 키워드/BM25 부스팅에 바로 쓰도록 **랭킹된 문자열 리스트**(중요도 순). 예: `["지게차", "적성검사", "면허", "갱신", "1종"]`.

> key_terms 는 추출 필드라 항목별 confidence 대신 **순위가 중요도를 인코딩**한다(요청 #5 예시도 문자열 목록). 나머지 추론 필드(legal_refs·entity_texts·responsible_unit)는 규칙 #6대로 confidence + evidence 를 포함한다.

> ⚠️ entity_texts·legal_refs 의 confidence 는 모두 매칭 강도에서 유도한 **미보정** 휴리스틱이다. BE2 는 상대 강도로만 사용.

## 테스트

```bash
python -m pytest app/tests/unit/test_department_assigner.py app/tests/unit/test_enrichment.py -q   # 55 passed (모델 불필요)
```

순수 로직(집계·키워드·LLM출력 환각방어·질의조립·entity_texts 정규화)만 검증한다. 임베딩 품질·실제 배정 정확도는 정답셋이 있어야 평가 가능하다.

> 참고: 본 작업 환경(샌드박스)은 파일 편집 직후 일부 .py 의 마운트 캐시가 지연되어 `service.py` 의 런타임 import 통합 테스트는 로컬에서 수행 권장. 통합 섹션 로직은 실제 함수로 시뮬레이션 검증했고, 정본 파일은 정상이다. 로컬 확인:
> `python -c "import asyncio; from app.structuring.service import StructuringService as S; print(asyncio.run(S().structure({'text':'가로등 파손 보수 요청','case_id':'T1'})).keys())"`
