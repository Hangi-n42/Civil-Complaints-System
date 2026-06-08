# BE3 핸드오프 — 법령 조문 인용 그라운딩 & 환각 검증

답변 초안에 "**건축법 제80조에 따르면…**" 같은 **조문 단위 근거**를 넣고, 검색된 조문에 없는 **환각 인용을 제거+플래그**한다. 기존 *유사 민원 사례* citation 과 별개의 **법령 인용** 레이어다.

## 제공물 (구현 완료, 테스트 통과)

`app/generation/citation/legal_citation.py` — 순수 로직 + 조문 검색 래퍼. 의존: `app/retrieval/law_article_store.py`(Hybrid 검색), `app/structuring/law_corpus.validate_citations`.

| 함수 | 역할 |
| --- | --- |
| `retrieve_legal_context(query, legal_refs, key_terms, top_k=5, store=None)` | **legal_refs 에 law_id 가 있을 때만** 조문 검색. 없으면 `[]`(그라운딩 생략). |
| `build_legal_context_block(articles)` | 검색 조문 → 프롬프트용 `[법령 조문]` 텍스트 블록. |
| `LEGAL_CITATION_INSTRUCTION` | "목록에 있는 조문만 인용" 프롬프트 지시 문자열. |
| `ground_legal_citations(answer_text, retrieved_articles)` | 답변 인용 추출→검증→**환각 제거+경고**. `{answer, valid, invalid, warnings}` 반환. |

**정책(합의)**: 환각 인용은 **제거 + 경고 플래그**(`[미검증 인용 제거]` 치환 + `warnings`). 그라운딩은 **legal_refs 있을 때만**.

## BE3 가 해야 할 배선 (3곳)

`app/generation/service.py` 의 `generate_qa(query, context, routing_trace)` 기준. BE1 구조화 결과(`legal_refs`, `key_terms`)를 generate_qa 로 전달할 수 있어야 한다(아래 `be1` 가정).

```python
from app.generation.citation.legal_citation import (
    retrieve_legal_context, build_legal_context_block,
    LEGAL_CITATION_INSTRUCTION, ground_legal_citations,
)

# ── (1) 생성 전: 조문 검색 + 프롬프트 주입 ────────────────────────────────
legal_articles = retrieve_legal_context(
    query, be1.get("legal_refs", []), key_terms=be1.get("key_terms"), top_k=5,
)
extra_prompt = ""
if legal_articles:                                  # legal_refs 있을 때만
    extra_prompt = LEGAL_CITATION_INSTRUCTION + "\n" + build_legal_context_block(legal_articles)
# extra_prompt 를 build_rag_prompt 의 프롬프트 끝에 append (PromptFactory 확장 or 문자열 결합)

# ── (2) LLM 생성 (기존 그대로) ────────────────────────────────────────────
# parsed = await self.parse_json_response(...)  # answer 포함

# ── (3) 생성 후: 인용 검증 + 환각 제거 ────────────────────────────────────
if legal_articles:
    grounded = ground_legal_citations(parsed["answer"], legal_articles)
    parsed["answer"] = grounded["answer"]            # 환각 인용 제거된 답변
    parsed["legal_citations"] = grounded["valid"]    # source_url 포함
    parsed["legal_citation_warnings"] = grounded["warnings"]
```

배선 위치 요약: `build_rag_prompt`(프롬프트 끝에 `extra_prompt` append) → 기존 생성 → 응답 dict 에 `legal_citations`/`legal_citation_warnings` 추가.

## 입력 계약 (BE1 → BE3)

- `legal_refs`: `[{"name","confidence","evidence","law_id","source"}]` — **`law_id` 필수**(조문 필터 키). 도메인 매칭도 사전에서 law_id 가 채워진다.
- `key_terms`: `["3톤 미만 지게차", ...]` — BM25 정확용어 부스트.
현재 generate_qa 는 이 둘을 받지 않으므로, 파이프라인에서 BE1 산출물을 generate_qa 로 넘기는 경로 추가가 필요하다.

## 반환 계약 (BE3 → FE)

```json
{
  "answer": "… 건축법 제80조에 따라 … [미검증 인용 제거]에 따라 …",
  "legal_citations": [
    {"law_name": "건축법", "article_no": "제80조", "law_id": "001823",
     "source_url": "http://www.law.go.kr/DRF/lawService.do?...&ID=001823", "verified": true}
  ],
  "legal_citation_warnings": ["미검증 인용 제거: 건축법 제999조"]
}
```

**FE 렌더링 메모**
- `legal_citations` 의 각 항목을 `source_url` 링크로 표시(검증된 조문만).
- `legal_citation_warnings` 가 있으면 "초안에서 미검증 법령 인용이 제거됨"을 검토자에게 노출.
- ⚠️ `source_url` 에 **크롤 OC 키가 포함**된다(`OC=donga…`). 사용자 노출용으로는 공개 URL 형식(`https://www.law.go.kr/법령/건축법`)으로 치환 권장.

## 선행 조건 / 한계

- **Dense 인덱스(bge-m3, GPU)를 빌드해야** 의미검색이 동작. 미빌드 시 `search()` 는 **BM25 단독 폴백**(정확용어 위주, 동작은 함). 빌드: `EMBEDDING_DEVICE=cuda python -c "from app.retrieval.law_article_store import get_law_article_store as g; print(g().build_index(rebuild=True))"`
- 인용 추출은 `'○○법 제□조'` 패턴 기반. 답변이 다른 형식(예: 법령명 생략)으로 인용하면 누락될 수 있음 → 프롬프트 지시로 형식 유도.
- confidence/검색 정확도는 법령 정답셋이 없어 미보정. 조문 인용은 법률자문이 아님을 답변에 명시 권장.

## 테스트

```bash
python -m pytest app/tests/unit/test_legal_citation.py -q     # 10 passed (모델 불필요)
```
검증된 동작(실 코퍼스 17,759조문, BM25): "무허가 가설건축물 이행강제금" → 건축법 제80조/제20조 검색·주입 → 초안의 `제999조`(환각) 제거, 제80조/제20조 valid+source_url 유지.
