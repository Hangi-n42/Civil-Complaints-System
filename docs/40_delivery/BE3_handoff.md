# BE3 핸드오프 — 답변 생성기가 받는 구조화 신호 + 법령 조문 인용

BE3(`GenerationService.generate_qa`)가 BE1 구조화·Phase B 조문 검색에서 **무엇을 받고, 무엇이 이미 배선됐고, 무엇을 추가로 쓰면 되는지** 설명합니다.

---

## 1. BE3가 BE1 구조화에서 받는 것 (답변 컨텍스트)

`structure()` 결과 dict에 답변 생성에 쓸 신호가 들어 있습니다.

| 필드 | 용도(BE3) |
| --- | --- |
| `observation/result/request/context` | 4요소 — 민원의 핵심을 답변 도입·요지로 |
| `roles{complainant, respondent, object}` | 민원인/유발자/조치객체 — 답변 주어·대상 명확화 |
| `request` + `issue_type` | "무엇을 요구/문의"하는지 → 답변 방향 결정 |
| `key_terms` | 검색·요지 강조어 |
| `legal_refs`(+`law_id`) | 관련 법령 후보 → 조문 인용의 출발점(§3) |
| `responsible_unit` | "○○과로 안내드립니다" 류 안내 |
| `urgency.level` | 답변 톤·처리 시급성 안내(긴급일수록 즉시 조치 강조) |

> ⚠️ 모든 confidence는 미보정 휴리스틱 → 답변에 단정적 수치로 노출하지 말고 보조 신호로만.

---

## 2. 법령 조문 인용 — **이미 generate_qa에 배선 완료**

"건축법 제80조에 따르면…"처럼 **조문 단위 근거**를 답변에 넣고, 검색되지 않은 **환각 인용을 자동 제거**합니다. BE3는 추가 코드 없이 동작하며, 결과 dict에 필드만 늘어납니다.

### 동작 (자동, `ENABLE_LEGAL_CITATIONS=true` 기본)
```
질의 → 법령 후보(law_id) → law_articles_v1(Dense+BM25) 조문 검색
     → 프롬프트에 [법령 조문] 블록 주입 → LLM 생성
     → 답변의 (법령명, 제○조) 인용을 검색 조문과 대조
       · 검색결과에 있으면 valid (+ public_url)
       · 없으면 환각 → 답변에서 제거 + 경고
```

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
     "source_url": "http://www.law.go.kr/DRF/...&ID=001823",   // 내부용(OC키 포함)
     "public_url": "https://www.law.go.kr/법령/건축법/제80조",  // FE 표시용(OC키 없음)
     "verified": true}
  ],
  "legal_citation_warnings": ["미검증 인용 제거: 건축법 제999조"]
}
```

### 전제 / 플래그
- **Dense 인덱스(law_articles_v1) 필요**: 로컬에서 `LawArticleStore.build_index()` 1회. 미빌드 시 BM25 단독 폴백(동작은 함).
- `ENABLE_LEGAL_CITATIONS=false` 로 끌 수 있음. 인덱스/모델 미가용이면 자동 무동작(legal_citations 키 없음).
- 헬스체크: `python scripts/check_law_index.py`.

> 상세: `docs/40_delivery/BE3_legal_citation_handoff.md`, 설계 `docs/60_specs/legal_corpus_phase_b.md`.

---

## 3. BE3가 추가로 할 수 있는 것 (선택)

- **법령 필터 정확도↑**: 현재 generate_qa는 *질의 텍스트*로 법령 후보를 자체 추출합니다. BE1이 이미 만든 `legal_refs`(정확한 law_id)를 generate_qa로 넘기면 더 정확합니다 — 필요 시 `generate_qa(query, context, be1_legal_refs=...)` 식 시그니처 확장을 요청하세요(미적용).
- **urgency 반영**: `candidate["urgency"]["level"]`이 "긴급/높음"이면 답변 서두에 즉시 조치·연락처 안내를 강화.
- **인용 검증 직접 호출**: 자체 생성 답변에 대해 `law_corpus.validate_citations(인용목록, 검색조문)`로 환각만 거를 수도 있음.

---

## 4. 주의 (정직)
- **조문 인용은 고위험**: 인덱스가 현행 스냅샷이므로, 개정 시 재인덱싱 안 하면 폐지·개정 조문을 인용할 수 있습니다. "법률자문이 아님" 고지 권장.
- 인용은 **검색된 조문 메타에서만** 채워지므로 `제○조` 번호 환각은 구조적으로 차단되나, *법령 선택 자체*가 틀릴 수 있음(soft 후보).
- `source_url`에는 크롤 OC 키가 있으니 사용자 노출은 `public_url`만.
