# BE2 핸드오프 — BE1 구조화 고도화 산출물 (검색 rerank 신호)

BE2가 요청한 6개 항목을 BE1 구조화 결과(`StructuringService.structure()`)에 추가 완료했습니다.
이 문서는 **무엇이 어떻게 구현됐고, BE2가 어떻게 받아 soft-rerank에 쓰는지**를 설명합니다.

---

## 1. 요청 ↔ 구현 매핑

| BE2 요청 | 구현 필드(키) | 상태 | 비고 |
| --- | --- | --- | --- |
| ① normalized_entities | **`entity_texts`** | ✅ | 이름만 다름(아래 주의 참고) |
| ② legal_refs | **`legal_refs`** | ✅ | `law_id`·`source` 추가(더 풍부) |
| ③ responsible_unit | **`responsible_unit`** | ✅ | 플래그 on + 인덱스 필요(아래) |
| ⑤ key_terms | **`key_terms`** | ✅ | 랭킹된 문자열 3~8개 |
| ⑥ confidence + evidence | 모든 추론 필드 포함 | ✅ | 미보정(soft 신호 전용) |
| (보너스) 긴급도 | **`urgency`** | ✅ | Track B 산출(검색엔 선택) |

MVP 4개(① ② ③ ④) 모두 제공됩니다.

---

## 0. 입력 정합 — **구조화 입력과 검색 색인 본문 분리** (중요)

원천 `consulting_content` = `제목 + Q(민원인) + A(상담사)`. 구조화 입력에는 **민원인 제목과 질문만** 사용하고, 검색 색인 본문은 `search_text`로 상담사 답변을 별도 보강합니다.

- 전처리 산출물: `data/processed/processed_consulting_data.json` (3,280건, 파싱 100%). 규칙: `docs/QUICK_START.md`.
- **어댑터 사용**: `app.structuring.preprocessing.to_structuring_record(rec)` → `structure()` 입력 dict 생성.
  - 구조화 입력 텍스트 = `title + client_question`. 파싱 결과 필드는 `title/client_question/consultant_answer`로 분리 보존한다.
  - Q가 비면 title 사용, Q가 제목을 참조("제목 내용처럼")해도 중복 없이 결합.
- **검색 색인 본문**: `scripts/build_index.py`는 `search_text`가 있으면 이를 BE2 `/api/v1/index`의 `text`로 사용한다. 과거 상담 데이터의 `search_text`는 `title + client_question + consultant_answer`, 신규 민원은 답변이 없으므로 `title + client_question`이 된다.
- `structure()`에 원천 `consulting_content`를 넘겨도 어댑터가 제목/질문/답변을 분리하고, 구조화 입력에는 민원인 원문만 사용합니다.
- **긴급도 모델 재학습 완료**: 입력을 상담사 포함 → 민원인 원문으로 교정하니 macro-F1 0.583 → **0.599**(보통 recall 균형). `urgency/dataset.py`가 processed 파일을 조인.

```python
from app.structuring.preprocessing import load_processed, to_structuring_record
recs = load_processed("data/processed/processed_consulting_data.json")
out  = await structuring_service.structure(to_structuring_record(recs[0]))
```

---

## 2. 실제 산출 예시 (검증된 출력)

입력 민원: *"3톤 미만 지게차 조종 면허 적성검사 갱신 절차가 궁금합니다. 1종 보통 면허도 있어야 하나요?"* (category=건설기계과)

```jsonc
{
  "case_id": "CASE-EX",
  // ① 정규화 객체 (요청의 normalized_entities)
  "entity_texts": [
    {"text": "지게차", "label": "OBJECT", "confidence": 0.9, "evidence": ["미만 지게차"]}
  ],
  // ② 법령 후보
  "legal_refs": [
    {"name": "건설기계관리법", "confidence": 0.6, "evidence": ["지게차"],
     "source": "domain", "law_id": "000239"}
  ],
  // ③ 담당부서 후보 (플래그 on 시 채워짐)
  "responsible_unit": [],
  // ⑤ 핵심 키워드
  "key_terms": ["지게차", "적성검사", "면허", "갱신", "조종"]
}
```

---

## 3. 필드별 상세 스키마

### ① `entity_texts` (= normalized_entities)
```jsonc
[{"text": "지게차",        // ← 정규화된 표준 객체명 (요청의 canonical)
  "label": "OBJECT"|"FACILITY",  // ← 요청의 type
  "confidence": 0.8~0.9,
  "evidence": ["미만 지게차"]}]  // ← 원문 근거 span (요청의 raw 표현)
```
- "3톤 미만 지게차" / "소형 지게차" → `text: "지게차"` 로 정규화. evidence에 원문 표현.
- 2026-06-09 BE1 entity 고도화: `가로등`·`보안등`·`공원등`·`도로등`·`조명등`·`LED등` 계열은 `text: "가로등"`으로 묶고, 실제 표현은 evidence에 보존합니다. BE2는 조명 계열 객체 일치 신호를 같은 축으로 약하게 가산하면 됩니다.
- 교통/도로/상하수/폐기물/주거/복지/행정 객체 사전을 확장했습니다. 예: `버스`, `철도`, `횡단보도`, `하수구`, `상수도`, `종량기`, `공동주택`, `청년월세`, `지역사랑상품권`.
- 2026-06-10 추가 고도화: 문화/예약(`공연`, `티켓`, `예매`, `투어`, `회원계정`), 노동/고용(`임금체불`, `고용보험`, `근로계약`), 기업/무역(`정책자금`, `수출입`, `세무신고`, `지원사업`), 건설/주택/자동차(`건설공사`, `하도급`, `분양`, `자동차등록`, `화물운송`) 행정 객체를 보강했습니다.
- 오탐 방지: `도로법`, `도로교통법`, `도로관리청`, `도로점용`처럼 법령·기관·제도 인용 문맥의 `도로`는 entity_texts에서 제외하고, 실제 대상물로 나온 `도로가 파손` 같은 문맥만 남깁니다.
- ⚠️ **이름 차이**: 우리는 `entity_texts`로 명명(요청은 normalized_entities). 의미는 동일. BE2에서 `text=canonical, label=type, evidence[0]=raw`로 매핑하면 됩니다. (원하면 별칭 키 추가 가능 — 요청 주세요.)
- confidence: canonical 직접 등장 0.9 / 변이 정규화 0.85 / 규칙 NER 흡수 0.8.
- 로컬 실측: `data/processed/processed_consulting_data.json` 3,280건 기준 lexicon-only 커버리지는 660건(20.12%) → 2,402건(73.23%), 규칙 NER+lexicon 커버리지는 1,521건(46.37%) → 2,525건(76.98%)로 개선됐습니다.
- `civil_cases_v1` 9,132건 기준 현재 저장 metadata는 1,007건(11.03%)이지만, 같은 document text에 개선된 BE1 entity 로직을 적용하면 6,769건(74.12%)까지 적재 가능할 것으로 예상됩니다. BE2 재인덱싱 또는 metadata backfill 후 아래 명령으로 실제 적재율을 재측정해 주세요.
  ```bash
  python scripts/check_chromadb_search_signal_coverage.py --persist-dir data/chroma_db --collection civil_cases_v1
  ```

### ② `legal_refs`
```jsonc
[{"name": "건설기계관리법", "confidence": 0.6~0.95,
  "evidence": ["지게차"],
  "law_id": "000239",     // ★ Phase B 조문 검색의 법령 필터 키 (요청엔 없던 보너스)
  "source": "name_match|abbr_match|ordinance|domain"}]  // 매칭 경로
```
- 법제처 현행법령 사전(5,585) + 부산 자치법규(9,086) 직접 매칭 + 도메인 트리거(18법령) 병합.
- `source`: 법령명/약칭 직접 등장(name/abbr_match), 부산 조례(ordinance), 어휘 추론(domain).
- `law_id`는 BE3의 조문 인용에 직결됩니다(BE2는 무시해도 됨).

### ③ `responsible_unit`
```jsonc
[{"name": "건설기계과", "confidence": 0.78, "evidence": ["지게차", "건설기계"], "source": "be1_structured"}]
```
- **부산시 실제 부서명**(busan_departments_master.json 118부서/2,114업무)을 bge-m3로 검색해 반환 → 환각 0.
- **출처 계약**: 실제 BE1 담당부서 추론 결과는 `source: "be1_structured"`를 포함합니다. 후보가 없으면 `responsible_unit: []`가 정상입니다. category/source 기반 fallback을 생성하는 경로는 반드시 `source: "category_source_fallback"`로 구분해야 하며, BE2 metadata에는 `responsible_units_source`로 보존합니다.
  ```jsonc
  // BE1 구조화 후보
  {"responsible_units": "건설기계과", "responsible_units_source": "be1_structured"}
  // category/source fallback
  {"responsible_units": "국토교통부", "responsible_units_source": "category_source_fallback"}
  ```
- ⚠️ **기본 비활성**: 임베딩 인덱스(bge-m3/Chroma)가 무거워 `ENABLE_RESPONSIBLE_UNIT=false`가 기본이라 `[]`로 나옵니다. 켜는 법:
  ```bash
  python -c "from app.structuring.department_assigner import get_department_assigner as g; print(g().build_index(rebuild=True))"
  export ENABLE_RESPONSIBLE_UNIT=true   # (선택) RESPONSIBLE_UNIT_USE_LLM=true 로 LLM 재랭킹
  ```
- **신뢰도 하한(#346)**: `RESPONSIBLE_UNIT_MIN_CONFIDENCE`(**기본 0.0**). bge-m3 raw cosine이 0.5~0.65 좁은 띠에 뭉쳐 단일 하한으로 정답/오답 분리가 불가함이 확인됨(오답 0.63 > 정답 0.57). Phase 2 이후 confidence는 raw cosine이 아니라 질의 내부 마진/합의 기반 상대 신호입니다. BE2는 여전히 hard filter가 아니라 **soft-rerank 가중치**로만 사용하세요.
- 미가용/실패 시 `[]`로 안전 폴백(파이프라인 영향 없음).
- ⚠️ **커버리지 한계(정직)**: 마스터는 **부산시 본청 부서**만 담습니다. 건설기계조종사면허(지게차)처럼 실무가 구청/공단 소관인 민원은 정답 부서가 풀에 없어 약하게 나옵니다(soft 후보로만 쓰세요). 마스터를 바꾸면 **인덱스 재빌드 필수**(`build_index(rebuild=True)`).
- **평가(#346 Phase 0)**: `scripts/eval_responsible_unit.py`로 Recall@3/MRR@3/NONE 무답률을 측정합니다. `data/departments/eval/responsible_unit_eval.jsonl` 100건 baseline은 Recall@3=0.5579, MRR@3=0.4632, NONE abstention=0.0000(threshold=0.4)입니다.
- **문서 확장(#346 Phase 1-A)**: 인덱싱 시 `DepartmentAssigner.build_index()`가 `부서명 + task + enrichment 사전 기반 확장어`를 임베딩 문서로 저장합니다. 확장은 `OBJECT_LEXICON`, `LEGAL_REF_LEXICON`, `FACILITY_KEYWORDS`의 트리거가 원문 부서/업무에 등장할 때만 적용하고, metadata의 `task`는 원문 그대로 유지합니다. 재인덱싱 후 after 평가는 Recall@3=0.6947(+0.1368p), MRR@3=0.6000(+0.1368p), NONE abstention=0.0000입니다. 즉 랭킹은 개선됐지만, 무답/신뢰도 분리는 Phase 2에서 별도로 다뤄야 합니다.
- **하이브리드 검색(#346 Phase 1-B)**: Dense+BM25+RRF 코드는 구현되어 있지만 기본값은 꺼져 있습니다(`RESPONSIBLE_UNIT_USE_HYBRID=false`). equal RRF와 Dense:BM25=2:1 가중 RRF 모두 100건 평가에서 Phase 1-A보다 낮아져 운영 기본값은 Dense Chroma 검색으로 유지합니다. 재실험 시에만 `RESPONSIBLE_UNIT_USE_HYBRID=true`로 켜세요. RRF 점수도 보정 확률은 아니므로, BE2는 계속 soft-rerank 신호로만 사용하세요.
- **상대 confidence(#346 Phase 2)**: `aggregate_candidates()`는 내부 `_rank_score`로 순위를 정하고, 출력 `confidence`는 top1/top2 마진, 같은 부서 multi-hit, evidence term 수, rank/gap decay로 별도 계산합니다. 100건 평가에서 Recall@3=0.6947, MRR@3=0.6000을 유지하면서 NONE abstention은 0.0000→0.8000(threshold=0.4)으로 개선됐습니다. 다만 아직 보정 확률은 아니고, 본청 마스터 밖 업무는 계속 낮은 신뢰/무답 후보로 처리해야 합니다.
- **CrossEncoder 리랭커(#346 Phase 3)**: `RESPONSIBLE_UNIT_USE_RERANKER=false`가 기본입니다. `true`로 켜면 `BAAI/bge-reranker-v2-m3`가 task 후보를 재점수화하지만, 100건 top_k_tasks=5 비교에서 Recall@3 0.6211→0.6421로 소폭 개선되는 수준이고 운영 기본 Phase 2 top_k_tasks=20(Recall@3=0.6947)보다 낮았습니다. CPU 비용도 커서 운영에서는 사용하지 않습니다.

### ⑤ `key_terms`
```jsonc
["지게차", "적성검사", "면허", "갱신", "조종"]   // 중요도 순 랭킹 문자열 3~8개
```
- entity_texts(객체) > 행정어 사전 > legal_refs 근거 순 가중. "신청/문의/절차" 같은 일반어 배제.
- 추출 필드라 항목별 confidence 대신 **순위가 중요도**를 인코딩.

---

## 4. BE2 연결 방법 (soft rerank)

1. **호출**: BE1 `structure(record)` → 위 필드가 포함된 dict 반환. (별도 API/엔드포인트는 기존 /search 파이프라인의 구조화 단계 산출물에 그대로 추가됨.)
2. **rerank 신호 사용**(BE2가 밝힌 soft-rerank 의도대로 — hard filter 아님):
   - **같은 `legal_refs.name`(또는 `law_id`)** → 후보 가점.
   - **`entity_texts.text` 겹침** → 객체 일치 가점.
   - **같은 `responsible_unit.name`** → 가점.
   - **`key_terms` 겹침** → BM25/키워드 부스트.
   - 각 신호를 **confidence로 가중**(높으면 강하게, 낮으면 약하게/무시) — 요청대로.
3. **임베딩/색인**: BE2가 민원을 인덱싱할 때 위 필드를 metadata로 넣어두면 rerank가 쉬워집니다(예: entity_texts/law_id를 chunk metadata로). `entity_texts`는 hard filter가 아니라 약한 soft rerank 신호로만 사용합니다.

---

## 5. 주의 (정직)

- **모든 confidence는 미보정(uncalibrated) 휴리스틱**입니다. `responsible_unit`은 Phase 2에서 상대 신뢰도로 개선됐지만, 절대 확률이 아닙니다. 절대 임계값 말고 **상대 강도·soft rerank**로만 — BE2의 설계 의도와 일치합니다.
- `legal_refs`·`responsible_unit`은 "검색 보조 후보"입니다. 틀릴 수 있어 hard filter 금지.
- `entity_texts` 이름이 요청의 `normalized_entities`와 다릅니다. 별칭이 필요하면 한 줄로 추가해 드립니다.

관련 상세 설계: `docs/60_specs/responsible_unit_assigner.md`.
