# Phase B — 조문 단위 법령 본문 코퍼스 + 검색 (설계 + 구현)

> 목표: 답변 초안에 "**건축법 제○조에 따르면…**"처럼 **조문 단위 정확한 근거**를 넣는다.
> Phase A(법령명/후보) 위에, `law_id` 를 다리로 삼아 조문을 검색한다.

## 구현 현황

| 구성 | 파일 | 상태 |
| --- | --- | --- |
| 조문 파서 + 인용 검증 | `app/structuring/law_corpus.py` | ✅ 구현·테스트 |
| 본문 수집 빌더(로컬) | `scripts/build_law_corpus.py` | ✅ 구현(화이트리스트 검증). **크롤은 로컬 실행** |
| 조문 인덱싱+검색 (Hybrid) | `app/retrieval/law_article_store.py` | ✅ 구현·테스트. Dense(bge-m3)+BM25 RRF. **Dense 인덱스 빌드는 로컬(GPU)** |
| 단위 테스트 | `test_law_corpus.py`(11) · `test_law_article_store.py`(10) | ✅ 통과 |

**실제 코퍼스로 검증된 것(이 환경, BM25 단독)**: `data/laws/law_articles.json` **17,759 조문**(법령 2,107 + 자치법규 15,652) 위에서 **Phase A→B 전 과정**이 동작:
- "무허가 가설건축물 이행강제금" → 건축법 **제80조(이행강제금)**·제20조(가설건축물)
- "지게차 조종 면허 적성검사" → 건설기계관리법 **제29조(정기적성검사)**·제27/28조(조종사면허)
- "실업급여 수급 자격" → 고용보험법 **제37조(실업급여의 종류)** 등
- "불법 주정차 단속 과태료" → 도로교통법 **제160조(과태료)** 등
- 인용 환각검증: 검색된 조문은 valid(+source_url), 가짜 `제999조` 는 invalid 로 차단.

> Dense(bge-m3)는 이 환경에 GPU/모델이 없어 미실행. **search() 는 Dense 미가용 시 BM25 단독으로 자동 폴백**하므로 위 검증이 가능했다. 로컬에서 GPU 인덱싱을 마치면 Dense+BM25 RRF 로 동작한다.

**로컬에서 할 것**: ① `build_law_corpus.py` 로 본문 크롤(OC 키) → `data/laws/law_articles.json`(완료, 17,759조문), ② `LawArticleStore.build_index()` 로 `law_articles_v1` Dense 인덱싱(GPU 권장).

> 주의: 본문 응답 스키마는 `parse_law_body` 가 방어적으로 파싱하나, 외부 API 미접근으로 **실제 lawService 응답으로 최초 1회 검증 필요**(빌더 주석의 SAMPLE URL). 필드 상이 시 `law_corpus.py` 의 키 후보만 조정.

## 1. 범위 (Scope / Non-goals)

- 대상: **핵심 현행법령**(민원에서 실제 등장하는 법령 — Phase A `legal_refs` 후보 세트) **+ 부산 자치법규(조례·규칙)**. 처음부터 전체 ~5천 법령을 넣지 않는다(노이즈·갱신비용).
- 검색 단위: **조(條)**. 항·호는 조 내부 구조로 보존.
- 본 단계 산출: 조문 코퍼스 JSON + Chroma 컬렉션 `law_articles_v1` + 검색 함수.
- Non-goal: 판례/해석례/행정규칙(이후 확장 여지로만 둠).

## 2. 데이터 출처 (법제처 OPEN API)

국가법령정보 공동활용 OPEN API. 인증 = OC(이메일 ID). **OC 키 보유 확인됨.**

| 용도 | 엔드포인트 | 핵심 파라미터 |
| --- | --- | --- |
| 법령 목록 | `lawSearch.do` | `OC, target=law, type=JSON, display, page, query` |
| 법령 본문(조문) | `lawService.do` | `OC, target=law, type=JSON, ID 또는 MST` |
| 자치법규 목록 | `lawSearch.do` | `target=ordin` |
| 자치법규 본문 | `lawService.do` | `target=ordin, ID` |

- 본문 응답은 **조문/항/호가 구조화**되어 제공되며, 조문번호·조문제목·조문내용·시행일자·소관부처 메타를 포함한다.
- 샘플(브라우저 확인용): `http://www.law.go.kr/DRF/lawService.do?OC=test&type=JSON&target=law&ID=011357`
- 무료·이메일 인증. 과도한 요청 금지(배치 sleep·캐싱 전제).

## 3. 수집 파이프라인 (Ingestion)

```
Phase A 사전(law_dictionary.json) ─┐
민원 빈출 법령 화이트리스트 ───────┼─▶ 대상 법령 ID 목록 확정
부산 자치법규(busan_ordinances)  ─┘
        │
        ▼  lawService.do(target=law|ordin, ID, type=JSON)
   법령 본문(JSON) ── 조문 파서 ──▶ 조(article) 단위 레코드
        │
        ▼  정규화/청킹
   law_articles.json   ──▶  인덱싱(다음 절)
```

1. **대상 확정**: Phase A 사전 + 민원 로그에서 실제 인용된 법령(legal_refs 누적)으로 화이트리스트 구성. 초기엔 수십 개로 시작해 점진 확장.
2. **본문 수집**: 법령 ID 별 `lawService.do` 호출. 응답에서 조문 배열 추출.
3. **조문 파싱**: 조문번호("제3조"), 조문제목, 조문내용(항·호 포함)을 1 조 = 1 청크로. 부칙·별표는 별도 type 태그.
4. **버전 관리**: 응답의 **시행일자**를 레코드에 박아 "현행" 스냅샷을 식별. (개정 시 재수집으로 교체)

## 4. 데이터 스키마 (조문 레코드)

```json
{
  "doc_id": "law:001234#제3조",
  "law_name": "건축법",
  "law_id": "001234",
  "article_no": "제3조",
  "article_title": "적용 제외",
  "text": "제3조(적용 제외) ① 다음 각 호의 ...",
  "enforce_date": "2025-01-01",
  "dept": "국토교통부",
  "doc_type": "law",            // law | ordinance | addendum
  "source_url": "http://www.law.go.kr/DRF/lawService.do?...&ID=001234"
}
```

## 5. 인덱싱

- 기존 인프라 재사용: **bge-m3 임베딩 + Chroma**. 신규 컬렉션 **`law_articles_v1`**(민원 사례 컬렉션과 분리).
- **Hybrid(BM25 + Dense) 권장**: 법조문은 정확 용어("적성검사", "가설건축물")가 결정적이라 BM25가 강하다. 기존 `app/retrieval/search/hybrid.py`(RRF) 패턴 재사용.
- 청크 = 조 1개. 메타로 law_id/article_no/enforce_date 필터 가능하게 인덱싱.

## 6. 검색 흐름 — Phase A 와의 연결점

```
민원 ─▶ BE1 구조화(legal_refs: 법령 후보 + law_id)
                │  (Phase A 산출물이 그대로 '법령 필터'가 됨)
                ▼
   law_articles_v1 에서 law_id ∈ {후보} 로 1차 필터
                ▼
   필터된 조문 풀에서 key_terms/질의로 조문 단위 Hybrid 검색 → Top 조문
                ▼
   BE3 답변 초안 컨텍스트(법령명 + 조문번호 + 조문내용)
```

`legal_refs` 후보가 **검색 공간을 법령 단위로 좁히는 필터** 역할을 하므로 Phase A→B가 자연히 이어진다. 후보 confidence 가 높으면 강한 필터, 낮으면 약한 필터(또는 전체 검색 fallback)로 운용.

## 7. 답변 생성(BE3)과 인용 환각 방지 ★

조문 인용은 틀리면 신뢰를 무너뜨리는 고위험 기능이다. 다음을 강제한다.

- LLM 은 **검색된 조문 컨텍스트 안의 것만** 인용한다.
- 출력의 (법령명, 조문번호)는 **검색 결과 메타와 사후 대조**해 불일치 시 폐기/경고. 모델이 "제○조"를 지어내지 못하게 한다.
- 인용에는 `source_url`(조문 직링크)을 첨부해 검증 가능하게 한다.
- (참고) 기존 오픈소스 MCP(`korean-law-mcp`)도 "LLM 환각 방지 인용검증"을 핵심 기능으로 둔다 — 동일 원칙.

## 8. 최신성/갱신

- **현행 vs 시행예정** 구분: 현행 스냅샷만 인덱싱(시행일자 ≤ 오늘). 시행예정은 별도 플래그.
- **정기 동기화**: 주간 배치로 화이트리스트 법령의 시행일자/개정 변경분 재수집 → 변경된 법령만 조문 교체(증분). 미동기화 시 폐지·개정 조문 인용 위험.
- 변경 감지: 법령 목록의 시행일자/제개정구분 비교.

## 9. 리스크 / 미결 (보수적)

- **정확성·라이선스**: 공공데이터지만 **캐싱·재배포 약관은 확인 불가 상태** → 전면 캐싱 전 약관 검토 필요. 조문 인용은 법률자문이 아님을 답변에 명시.
- **자치법규 본문 커버리지**: 부산 조례 중 일부는 본문 API 제공 범위·형식이 법령과 다를 수 있어 파서 분기 필요(확인 필요).
- **조문 매칭 정밀도**: 법령 필터 후에도 hybrid 가 아니면 엉뚱한 조문 가능 → BM25 병행 필수.
- **API 안정성/쿼터**: 무료지만 과도요청 제한·간헐 HTML 응답 가능 → 재시도·백오프·로컬 캐시.

## 10. Build vs Reuse

직접 구축(권장: 인덱스·필터를 BE2와 통합 제어) 외에, 참고/대안으로 기존 MCP 서버가 있다: `ChangooLee/mcp-kr-legislation`(132+ 도구), `chrisryugj/korean-law-mcp`(인용검증·조문 영향그래프). BE3 프로토타이핑엔 이들을 붙여 빠르게 검증하고, BE2 검색 코퍼스는 직접 인덱싱으로 가는 하이브리드 전략이 현실적이다.

## 11. 로컬 실행 순서

```bash
# 1) 조문 본문 크롤 (핵심 국가법령 18 + 부산 본청 조례 1,193)
export LEGISLATION_API_KEY=<OC 아이디>
python scripts/build_law_corpus.py            # → data/laws/law_articles.json
#   (구·군 조례까지: --all-ordinances / 법령 추가: --laws "법령명" ...)

# 2) Dense 인덱싱 (bge-m3, GPU 권장 — 17,759조문)
EMBEDDING_DEVICE=cuda python -c "from app.retrieval.law_article_store import get_law_article_store as g; print(g().build_index(rebuild=True))"

# 3) 검색 (Phase A 후보로 법령 필터)
python - <<'PY'
from app.structuring.legal_dictionary import get_legal_ref_matcher
from app.retrieval.law_article_store import get_law_article_store
q = "무허가 가설건축물 이행강제금 기준"
law_ids = [r["law_id"] for r in get_legal_ref_matcher().match(q) if r.get("law_id")]
print(get_law_article_store().search(q, law_ids=law_ids, key_terms=["가설건축물","이행강제금"]))
PY
```

BE3 인용 시 `law_corpus.validate_citations(인용목록, 검색조문)` 으로 (법령명·조문번호)를 검색결과와 대조해 환각을 폐기/플래그한다.

## 12. 구현 완료 / 남은 작업

**완료**
- **BM25+RRF Hybrid**: Dense(bge-m3) ⊕ Sparse(BM25). 한글 복합어 대응 위해 **문자 bigram 토큰화**(예: '조종사면허'↔'면허', '정기적성검사'↔'적성검사'). Dense 미가용 시 BM25 단독 폴백.
- **Phase A↔B 완전 연결**: 도메인 lexicon 으로만 매칭된 `legal_refs` 도 사전에서 `law_id` 를 해석해 채운다 → 법령명이 직접 안 적힌 민원도 조문 검색 필터가 걸린다.
- 자치법규 본문 파싱(조문여부="Y", 조문번호=리스트, 조내용/조제목 필드) 수정.

**BE3 인용 그라운딩 (배선 완료)**
- `app/generation/citation/legal_citation.py` + **`generate_qa` 배선 적용**: 질의→법령 후보(law_id)→조문 검색→프롬프트 `[법령 조문]` 주입→답변 인용 검증·**환각 제거+경고**. `ENABLE_LEGAL_CITATIONS`(기본 on, 인덱스/모델 미가용 시 자동 무동작). 반환에 `legal_citations`(+`public_url`)·`legal_citation_warnings` 추가.
- **공개 URL**: `law_corpus.public_law_url()` 로 OC 키 없는 `https://www.law.go.kr/법령/{법령명}/{조문}` 부착(FE는 `public_url` 렌더).
- 헬스체크: `scripts/check_law_index.py`(색인 수·검색·인용검증 점검).

**남은 작업**
- 주간 동기화 배치(시행일자/개정 변경분 증분 갱신).
- (선택) RRF 가중치·BM25 파라미터 튜닝, 형태소 분석기 도입 검토.

---

### Sources
- [국가법령정보 공동활용 OPEN API 가이드](https://open.law.go.kr/LSO/openApi/guideList.do)
- [법제처 국가법령정보 공유서비스 — 공공데이터포털](https://www.data.go.kr/data/15000115/openapi.do)
- [mcp-kr-legislation (참고 구현)](https://github.com/ChangooLee/mcp-kr-legislation)
- [korean-law-mcp (인용검증 참고)](https://github.com/chrisryugj/korean-law-mcp)
