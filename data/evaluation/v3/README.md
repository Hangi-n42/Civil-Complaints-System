# V3 검색 평가셋 — 파일 가이드 (Single Source of Truth)

평가 qrels/queries 파일이 여러 버전으로 난립해 어느 것이 정답인지 혼란이 있었다.
이 문서가 **canonical 파일**과 나머지의 계보를 정리한다.

## ✅ Canonical (이것만 쓸 것)

| 용도 | 파일 | 내용 |
|---|---|---|
| **평가용 정답표** | `qrels_pooled_3judge.tsv` | 공정 풀(Dense∪BM25 top-50) + 3-채점관 median. **최종 평가는 이걸로.** (8,057쌍) |
| 베이스 qrels | `qrels.tsv` | 100쿼리 relabel + #262 reranker pool (2,549쌍). `qrels_pooled*`의 모태 |
| 쿼리 | `queries.jsonl` | 100쿼리 (4요소 구조화) |
| 코퍼스 | `corpus_meta.json` | 9,132 case |

평가 실행: `QRELS_POOLED_FILE=qrels_pooled_3judge.tsv python scripts/eval_noself.py`
자세한 정비 내역: `docs/20_domains/retrieval/eval_overhaul_summary.md`

## 보조 (현행 100쿼리 라인)

| 파일 | 비고 |
|---|---|
| `qrels_pooled.tsv` | 2-채점관 floor 버전 (3-채점관과 비교용 보존) |
| `pool_to_judge.tsv` | 공정 풀 채점 대상 5,508쌍 |
| `checkpoints/fair_pool*.json` | 채점관별 원점수 (exaone/gemma/ax4/qwen) |

## 🗄️ archive/ (구버전·미사용 — 참조용 보존, 평가에 쓰지 말 것)

| 파일 | 정체 |
|---|---|
| `archive/qrels_100.tsv` | `qrels.tsv`의 #262 이전 스냅샷 (2,348쌍) |
| `archive/qrels_112.tsv`·`archive/qrels_original.tsv` | 폐기된 112쿼리 확장 시도 (2,771쌍) |
| `archive/queries_112.jsonl` | 112쿼리 세트 (미채택) |

## 구 lineage (이미 커밋된 옛 평가셋)

| 파일 | 정체 |
|---|---|
| `qrels_final.tsv` | 초기 49쿼리 평가셋 (749쌍) |
| `qrels_original_llm.tsv` | 최초 LLM 라벨링, 0~3 옛 척도 (50쿼리, 767쌍) |

> 참고: 평가 데이터의 줄바꿈은 루트 `.gitattributes`로 LF 고정됨 (Windows CRLF churn 방지).
