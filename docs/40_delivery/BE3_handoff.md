# BE3 핸드오프 — 답변 생성기가 받는 구조화 신호 + 법령 조문 인용

BE3(`GenerationService.generate_qa`)가 BE1 구조화·Phase B 조문 검색에서 **무엇을 받고, 무엇이 이미 배선됐고, 무엇을 추가로 쓰면 되는지** 설명합니다.

---

## 1. BE3가 BE1 구조화에서 받는 것 (답변 컨텍스트)

`structure()` 결과 dict에 답변 생성에 쓸 신호가 들어 있습니다.

| 필드 | 용도(BE3) |
| --- | --- |
| `observation/result/request/context` | 4요소 — 민원의 핵심을 답변 도입·요지로 |
| `roles{complainant, respondent, object}` | 민원인/유발자/조치객체 — 답변 주어·대상 명확화 |
| `request` + `key_terms` | "무엇을 요구/문의"하는지 → 답변 방향 결정 |
| `key_terms` | 검색·요지 강조어 |
| `legal_refs`(+`law_id`) | 관련 법령 후보 → 조문 인용의 출발점(§3) |
| `responsible_unit` | "○○과로 안내드립니다" 류 안내 |
| `urgency.level` | 답변 톤·처리 시급성 안내(긴급일수록 즉시 조치 강조) |

> ⚠️ 모든 confidence는 미보정 휴리스틱 → 답변에 단정적 수치로 노출하지 말고 보조 신호로만.

---

## 2. 법령 조문 인용 — **generate_qa와 /qa 응답에 배선 완료**

"건축법 제80조에 따르면…"처럼 **조문 단위 근거**를 답변에 넣고, 검색되지 않은 **환각 인용을 자동 제거**합니다. BE3는 추가 코드 없이 동작하며, 결과 dict에 필드만 늘어납니다.

### 동작 (자동, `ENABLE_LEGAL_CITATIONS=true` 기본)
```
BE1 query_signals(legal_ref_ids/key_terms) → law_articles_v1(Dense+BM25) 조문 검색
     → 프롬프트에 [법령 조문] 블록 주입 → LLM 생성
     → 답변의 (법령명, 제○조) 인용을 검색 조문과 대조
       · 검색결과에 있으면 valid (+ public_url)
       · 없으면 환각 → 답변에서 제거 + 경고
```

`query_signals`가 없거나 `legal_ref_ids`가 비어 있으면 이전 호출자와의 호환을 위해
BE3가 질의 텍스트에서 법령 후보와 핵심어를 다시 추출한다.

### `generate_qa` 반환 (기존 + 추가)
```jsonc
{
  "question": "...",
  "answer": "… 건축법 제80조에 따라 … [미검증 인용 제거]도 적용 …",  // 환각 제거됨
  "confidence": 0.7,
  "citations": [ ... ],                 // 기존: 유사 민원 사례 인용
  "limitations": "...",
  "model": "...",
  // ── 신규(법령 조문) ──
  "legal_citations": [
    {"law_name": "건축법", "article_no": "제80조", "law_id": "001823",
     "public_url": "https://www.law.go.kr/법령/건축법/제80조",
     "verified": true}
  ],
  "legal_citation_warnings": ["미검증 인용 제거: 건축법 제999조"]
}
```

`/api/v1/qa` 통합 응답에서도 위 두 필드를 유지한다. 법령 그라운딩이 비활성화되거나
검색 결과가 없으면 키를 생략하지 않고 각각 빈 배열(`[]`)로 반환한다.

### 전제 / 플래그
- **Dense 인덱스(law_articles_v1) 필요**: 로컬에서 `LawArticleStore.build_index()` 1회. 미빌드 시 BM25 단독 폴백(동작은 함).
- `ENABLE_LEGAL_CITATIONS=false` 로 끌 수 있음. 인덱스/모델 미가용이면 자동 무동작하며 `legal_citations: []`를 반환한다.
- 헬스체크: `python scripts/check_law_index.py`.

> 상세: `docs/40_delivery/BE3_legal_citation_handoff.md`, 설계 `docs/60_specs/legal_corpus_phase_b.md`.

---

## 3. BE1 신호 전달과 긴급도 반영 — **적용 완료**

`/api/v1/qa` 요청은 검색 API와 같은 `query_signals` 객체를 선택적으로 받는다.

```jsonc
"query_signals": {
  "legal_ref_names": ["건축법"],
  "legal_ref_ids": ["001823"],
  "key_terms": ["가설건축물", "이행강제금"],
  "responsible_units": ["건축과"],
  "urgency_level": "높음"
}
```

- `legal_ref_ids`와 `key_terms`는 조문 검색에 직접 사용한다.
- 같은 신호를 내부 유사 민원 검색의 metadata soft rerank에도 전달한다.
- `urgency_level`이 `긴급` 또는 `높음`이면 안전 안내를 강화한다.
- 긴급도는 미보정 보조 신호이므로 원문에 즉시 위험 근거가 있을 때만 112/119 안내를 사용한다.
- 확인되지 않은 부서명, 전화번호, 처리기한은 생성하지 않도록 프롬프트에서 제한한다.
- 별도의 `validate_citations()` 직접 호출은 추가하지 않는다. 기존 생성 후
  `ground_legal_citations()` 경로가 검증과 제거를 담당한다.
- UI 검색은 `complaint_id`와 `query_signals`를 `/search`에 전달하고 검색 응답의
  `routing_hint`를 `/qa`에 그대로 계승한다.
- 검색 결과를 재사용하는 QA도 metadata soft rerank 후 grounding filter를 적용한다.
- `generation_metadata.legal_grounding_status`로 `disabled`, `no_candidates`,
  `grounded`, `error`를 구분한다.

---

## 4. 주의 (정직)
- **조문 인용은 고위험**: 인덱스가 현행 스냅샷이므로, 개정 시 재인덱싱 안 하면 폐지·개정 조문을 인용할 수 있습니다. "법률자문이 아님" 고지 권장.
- 인용은 **검색된 조문 메타에서만** 채워지므로 `제○조` 번호 환각은 구조적으로 차단되나, *법령 선택 자체*가 틀릴 수 있음(soft 후보).
- 공개 `/qa` 응답은 `source_url`과 OC 키를 제거하며 `public_url`만 노출한다.

---

## 5. 팀별 전달사항

### 5.1 BE1에 전달

BE3는 BE1 구조화 결과를 `/search`와 `/qa`의 `query_signals`로 전달받아 검색 보정,
법령 조문 검색, 긴급 안내에 사용한다.

필수 유지 필드:

| BE1 구조화 필드 | 전달되는 query signal | BE3 사용처 |
| --- | --- | --- |
| `entity_texts[].text` | `entity_texts[]` | 유사 민원 metadata soft rerank |
| `legal_refs[].name` | `legal_ref_names[]` | 법령명 표시 및 후보 추적 |
| `legal_refs[].law_id` | `legal_ref_ids[]` | `law_articles_v1` 조문 검색 |
| `key_terms[]` | `key_terms[]` | 검색 및 법령 BM25 보강 |
| `responsible_unit[].name` | `responsible_units[]` | 담당부서 후보 안내 |
| `urgency.level` | `urgency_level` | 답변 안전 안내 보조 |

BE1 확인사항:

- 구조화/검색 입력에는 민원인 원문과 상담사 답변을 함께 사용한다. 단, 파싱 결과는 `client_question`과 `consultant_answer`를 분리 보존한다.
- `legal_refs`와 `responsible_unit`은 확정값이 아닌 후보이므로 빈 배열을 허용한다.
- `legal_ref_ids`와 `legal_ref_names`는 가능하면 동일 항목 순서로 생성한다.
- confidence는 미보정 값이므로 답변 본문에 수치로 노출하지 않는다.
- `hybrid/llm/fallback` 구조화에서는 부정확한 evidence span 때문에 전체 처리를 실패시키지 않는다.
- ingestion의 `deduplicate()`는 동일·근접 중복 문서를 제거하므로 원본 건수와 처리 건수가 달라질 수 있다.

### 5.2 BE2에 전달

BE2 검색은 BE1의 `query_signals`를 hard filter가 아닌 soft rerank 신호로 사용한다.
UI 검색과 `/qa` 내부 검색 모두 같은 신호를 전달한다.

BE2 확인사항:

- `/api/v1/search` 응답의 `routing_hint`와 `routing_trace`는 이후 `/api/v1/qa`가 그대로 계승한다.
- `route_key`와 `strategy_id`를 검색 이후 임의로 재계산하거나 변경하지 않는다.
- 인덱싱 metadata에 `entity_texts`, `legal_ref_names`, `legal_ref_ids`,
  `key_terms`, `responsible_units`, `urgency_level`을 유지한다.
- 기존 검색 결과를 QA에 재사용할 때도 metadata soft rerank 후 grounding filter를 적용한다.
- grounding filter 결과가 0개면 사용자용 `/qa`는 `no_evidence_fallback`을 반환한다.
- 과거 Chroma collection에는 신규 metadata가 없을 수 있으므로 필요하면
  `scripts/backfill_chromadb_search_signals.py`를 실행하고 필드 적재율을 확인한다.

검색 결과에서 QA로 반드시 전달할 값:

```jsonc
{
  "complaint_id": "CMP-2026-0001",
  "routing_hint": {
    "strategy_id": "topic_general_medium_v1",
    "route_key": "general/medium",
    "top_k": 5,
    "snippet_max_chars": 1100,
    "chunk_policy": "balanced"
  },
  "query_signals": {
    "legal_ref_ids": ["001823"],
    "key_terms": ["가설건축물", "이행강제금"]
  }
}
```

### 5.3 FE에 전달

`/api/v1/qa`는 `complaint_id`와 `routing_hint`가 필수다. FE는 `/search` 성공 응답의
`routing_hint`를 보존했다가 같은 민원의 `/qa` 요청에 전달해야 한다.

FE 요청 체크리스트:

- `complaint_id` 필수
- `query` 필수
- `/search`에서 받은 `routing_hint` 필수
- 가능한 경우 동일한 `query_signals` 전달
- 검색 결과 재사용 시 `use_search_results=true`와 최소 1개의 `search_results` 전달
- 다른 민원을 선택하면 이전 민원의 `routing_hint`를 재사용하지 않는다.

FE 응답 처리:

| 필드 | 처리 |
| --- | --- |
| `answer` | 민원 회신 본문 |
| `citations` | 유사 민원 근거. `doc_id/source/quote` 사용 |
| `legal_citations` | 검증된 법령만 표시. 링크는 `public_url`만 사용 |
| `legal_citation_warnings` | 미검증 법령 인용 제거 경고 표시 |
| `limitations` | 답변의 한계·fallback 사유 표시 |
| `generation_metadata` | fallback 및 법령 grounding 상태 표시 |
| `qa_validation` | 응답 스키마·citation token 검증 상태 |
| `search_trace` | 사용한 검색 건수와 컨텍스트 예산 |
| `citation_validation` | 검색 컨텍스트와 citation 일치 여부 |

`generation_metadata.legal_grounding_status` 해석:

- `grounded`: 법령 후보 검색과 인용 검증 수행
- `no_candidates`: 관련 조문 후보 없음
- `disabled`: 기능 비활성
- `error`: 법령 검색 또는 검증 실패
- `not_requested`: 법령 grounding을 요청하거나 수행하지 않은 응답

FE 금지사항:

- `source_url`, OC 키, 내부 DRF URL을 표시하거나 저장하지 않는다.
- API 오류 시 실제 행정 회신처럼 보이는 샘플 답변·가짜 citation·처리기한을 만들지 않는다.
- `hallucination_flag=true` 또는 `legal_citation_warnings`가 있으면 검토자 경고 없이 숨기지 않는다.
- 후보 confidence를 확정 확률처럼 표시하지 않는다.

---

## 6. 공통 정책

### 근거가 0개인 경우

- 사용자용 `/api/v1/qa`: HTTP 성공 응답과 `generation_mode=no_evidence_fallback`을 반환한다.
  답변은 사실을 단정하지 않고 담당부서의 사실관계 확인이 필요함을 안내한다.
- 평가·벤치마크용 PromptFactory autoretrieve: `NoEvidenceError`로 즉시 실패한다.
- 두 경로는 목적이 다르므로 평가 실패와 사용자용 fallback을 같은 지표로 집계하지 않는다.

### 품질 신호

- `citation_coverage`: 공개 답변에는 출처 토큰을 넣지 않으므로, 구조화 citation 중 검색 컨텍스트와 검증된 비율
- `segment_coverage`: 요청 segment 중 답변에서 다룬 segment 비율
- `hallucination_flag`: citation mismatch 또는 미검증 법령 인용 제거가 발생하면 `true`

품질 신호는 운영 진단용이며 단독으로 최종 답변 품질을 판정하지 않는다.

### 생성·검색 안전장치

- BE3 strict parser는 PromptFactory 스키마의 네 최상위 키만 허용한다:
  `citations`, `answer`, `limitations`, `structured_output`.
- Ollama 동적 JSON Schema로 citation과 필수 키를 제한하고, strict 파싱 실패는
  `default -> compact` 순서로 한 번만 재시도한다. 느슨한 파싱으로 성공 처리하지 않는다.
- grounding 후보는 단일 배치 판정을 우선 사용하며, 배치 응답 실패 시에만
  기존 후보별 병렬 판정으로 복귀한다.
- 검색 청크는 앞부분뿐 아니라 뒤쪽의 처리 결론·제약도 보존한다.
- 원문 레코드 autoretrieve는 현재 `case_id/source_id`를 검색 후보에서 제외해
  평가 대상 답안이 자기 근거로 재사용되는 누수를 막는다.
- `query_signals`는 기존 BE2 계약대로 soft rerank에만 사용하며 hard filter로 바꾸지 않는다.
- 법령 후보가 0개여도 답변에 임의 법령명이 있으면 검증 단계에서 제거한다.
- fast fallback은 검색 snippet이나 법령 조문을 회신 결론처럼 붙이지 않고,
  사실관계·소관 권한 확인이 필요하다는 제한 답변을 반환한다.
- 잘린 JSON에서 `answer`를 복구하지 못한 경우 첫 검색 snippet을 답변으로
  대체하지 않는다. 현재 민원과 다른 유사 사례가 회신으로 노출되는 것을
  막기 위해 제한 응답을 사용한다.
- 답변 후처리는 literal `\n`, 내부 섹션·액션 라벨, 미완성 `[REDACTED:`
  문자열을 제거하고 확인되지 않은 일정·현황과 강한 이행 약속을 검토
  표현으로 완화한다.
- `generation_metadata.answer_quality_warning_codes`에는
  `ANSWER_REQUEST_MISMATCH`, `PRECEDENT_FACT_LEAKAGE_RISK`,
  `UNSUPPORTED_COMMITMENT_RISK`, `UNVERIFIED_FACT_RISK`,
  `CONTEXT_CONSTRAINT_CONFLICT`가 기록될 수 있다. 이 경고가 있으면
  `quality_signals.hallucination_flag=true`로 전달한다.

---

## 7. 연동 완료 체크리스트

- [x] BE1 구조화 결과에서 `query_signals` 7종이 생성된다.
- [x] BE2 `/search`가 `query_signals`를 받고 metadata soft rerank에 사용한다.
- [x] `/search`의 `routing_hint`가 같은 민원의 `/qa`로 전달된다.
- [x] `/qa`가 `answer`, citation, 법령 인용, 검증·추적 필드를 반환한다.
- [x] 공개 응답 어디에도 `source_url` 또는 OC 키가 없다.
- [x] 근거 0개, 법령 후보 없음, 법령 검색 오류가 서로 다른 상태로 표시된다.
- [x] UI API 오류가 가짜 회신 답변으로 대체되지 않는다.

검증:

```powershell
.\.venv\Scripts\python.exe -m pytest app/tests/unit -q -p no:cacheprovider
.\.venv\Scripts\python.exe -m pytest app/tests/integration/test_week6_search_to_qa_e2e_sample10.py -q -p no:cacheprovider
python scripts/check_law_index.py
```

상세 계약:

- `docs/10_contracts/interfaces/week6/week6_be3_interface.md`
- `docs/40_delivery/BE2_structuring_handoff.md`
- `docs/40_delivery/BE3_legal_citation_handoff.md`
- `docs/40_delivery/FE_handoff.md`
