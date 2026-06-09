# BE2 운영 전 검색 readiness 점검

작성일: 2026-06-09  
담당: BE2 검색  
관련 이슈: #340  
기준 브랜치: `main` 최신 반영 후 점검

## 1. 목적

BE2 검색을 운영에 올리기 전, 실제 ChromaDB collection에 BE1 검색 신호 metadata가
충분히 적재되어 있는지 확인하고 운영 판단을 정리한다.

이 점검은 읽기 전용으로 수행했다. ChromaDB metadata, 검색 로직, rerank 가중치는
변경하지 않았다.

민원 원문, 검색 snippet, 생성 답변 미리보기 등 개인정보 위험이 있는 raw 내용은
리포트에 포함하지 않았다.

## 2. 실행 명령

```bash
python scripts/check_chromadb_search_signal_coverage.py --persist-dir data/chroma_db
```

생성 산출물:

- `reports/retrieval/v3/chromadb_search_signal_metadata_coverage.json`
- `reports/retrieval/v3/chromadb_search_signal_metadata_coverage.md`
- `reports/retrieval/v3/law_articles_index_check.md`

## 3. 전체 결과

| 항목 | 값 |
| --- | ---: |
| collection | `civil_cases_v1` |
| 전체 건수 | 9,132 |
| 점검 건수 | 9,132 |
| 제한 실행 | 아니오 |

## 4. 필드별 적재율

| 필드 | 적재 건수 | 적재율 | 판단 |
| --- | ---: | ---: | --- |
| `entity_texts` | 1,007 | 11.03% | 주의 |
| `legal_ref_names` | 3,885 | 42.54% | 주의 |
| `legal_ref_ids` | 3,885 | 42.54% | 주의 |
| `issue_types` | 6,726 | 73.65% | 통과 |
| `key_terms` | 7,379 | 80.80% | 통과 |
| `responsible_units` | 9,132 | 100.00% | 통과 |
| `urgency_level` | 9,132 | 100.00% | 통과 |

## 5. 운영 판단

BE2 검색은 운영 전 readiness 기준에서 **조건부 통과**로 판단한다.

통과 근거:

- 전체 9,132건 collection을 제한 없이 점검했다.
- `key_terms`, `issue_types`는 대부분의 문서에 적재되어 있어 soft rerank의 기본 신호로 사용할 수 있다.
- `responsible_units`와 `urgency_level`은 100% 적재되어 있다.
- `legal_ref_names`와 `legal_ref_ids`의 적재 건수와 비율이 동일해 법령명과 law_id 매핑 쌍은 일관되어 보인다.
- `entity_texts`, `key_terms`는 원문 값을 노출하지 않고 해시 prefix만 리포트에 남겼다.

주의 근거:

- `entity_texts` 적재율은 11.03%로 낮다. 객체명 기반 rerank 효과는 제한적으로 기대해야 한다.
- 법령 신호(`legal_ref_names`, `legal_ref_ids`) 적재율은 42.54%다. 법령 관련 질의에서만 강한 보조 신호로 해석해야 한다.
- `responsible_units` 100%는 과거 backfill의 category/source fallback 영향일 수 있다. 실제 BE1 `responsible_unit` 확정값과 동일하게 해석하면 안 된다.

## 6. 법령 조문 인덱스 확인

법령 조문 collection `law_articles_v1` 상태를 추가 확인했다.

확인 명령:

```bash
python scripts/check_law_index.py
python scripts/inspect_chromadb.py list
python scripts/inspect_chromadb.py count --collection law_articles_v1
```

확인 결과:

| 항목 | 결과 |
| --- | ---: |
| collection 존재 여부 | 존재 |
| collection 이름 | `law_articles_v1` |
| 색인 조문 수 | 17,759 |
| `law_id/law_name/article_no` 적재율 | 100.00% |
| 법령 필터 검색 | 정상 |
| 인용검증 | 정상 |

대표 질의에서 `건축법 제80조`, `건설기계관리법 제29조`, `고용보험법 제37조`,
`도로교통법 제160조` 등 관련 조문이 검색됐다. `scripts/check_law_index.py` 기준
검색된 조문 인용은 valid 처리되고, 검색되지 않은 조문 인용은 invalid로 차단됐다.

주의:

- ChromaDB metadata의 `source_url`은 내부 원천 확인용이다.
- FE/API 공개 응답에는 `source_url`을 노출하지 않고, 검증 경로에서 생성되는
  `public_url`만 노출한다.
- 법령 코퍼스가 갱신되면 `law_articles_v1` 재인덱싱이 필요하다.

## 7. 팀별 후속 확인

### BE1

- 실제 운영 구조화 결과에서 `entity_texts` 커버리지가 낮은 이유를 확인한다.
- `responsible_unit`이 실제 담당부서 후보인지, category/source fallback인지 구분 가능한 metadata가 필요할 수 있다.
- 법령 후보가 없는 민원은 정상적으로 빈 배열을 허용하되, 법령 관련 민원에서 law_id 매핑 누락이 없는지 확인한다.

### BE2

- `query_signals`는 계속 hard filter가 아니라 soft rerank 신호로 사용한다.
- `responsible_units`는 적재율이 높지만 fallback 가능성이 있으므로 가중치를 크게 올리지 않는다.
- 운영 모니터링에서는 metadata 적재율 리포트를 주기적으로 재실행한다.
- 검색 품질 이슈가 생기면 먼저 `entity_texts`와 법령 신호 적재율을 확인한다.

### BE3

- 법령 grounding 케이스에서는 BE2 검색 결과와 `generation_metadata.legal_grounding_status`를 함께 확인한다.
- 법령 후보가 없는 경우를 검색 실패로 단정하지 않는다.
- `fast_fallback` 비율은 BE3 생성 안정성 지표로 별도 모니터링한다.
- `law_articles_v1`는 현재 정상 확인됐으므로, 법령 citation 문제 발생 시 우선
  `legal_grounding_status`, `legal_citations`, `legal_citation_warnings`를 함께 확인한다.
- 공개 응답에는 `source_url`이 아니라 `public_url`만 노출한다.

### FE

- `/search` 응답의 `routing_hint`와 가능한 경우 `query_signals`를 `/qa`에 그대로 전달한다.
- 담당부서 후보는 확정 부서처럼 표시하지 않는다.
- 법령 citation은 검증된 `public_url`만 표시한다.

## 8. 운영 전 체크리스트

| 항목 | 상태 |
| --- | --- |
| ChromaDB metadata 적재율 전체 점검 | 완료 |
| `responsible_units` 적재율 확인 | 완료 |
| 법령명과 law_id 적재율 일치 확인 | 완료 |
| 법령 조문 collection `law_articles_v1` 확인 | 완료 |
| 법령 조문 검색 및 인용검증 확인 | 완료 |
| 법령 `source_url` 외부 노출 금지 확인 | 완료 |
| 검색 로직 변경 없음 확인 | 완료 |
| 개인정보 위험 raw 내용 미포함 확인 | 완료 |
| `entity_texts` 낮은 커버리지 후속 확인 | 필요 |
| `responsible_units` fallback 여부 후속 확인 | 필요 |

## 9. 결론

BE2 검색은 현재 인덱스 기준으로 운영 전 필수 metadata 점검을 통과했다.

다만 `entity_texts` 커버리지가 낮고, `responsible_units`가 실제 BE1 담당부서 후보인지
fallback 값인지 구분이 필요하다. 따라서 운영 투입은 가능하되, 초기 운영에서는
metadata 적재율과 `generation_metadata`를 함께 모니터링하는 조건부 통과로 기록한다.

추가로 법령 조문 인덱스 `law_articles_v1`는 17,759건 저장, 필수 metadata 적재,
법령 필터 검색, 인용검증이 모두 정상으로 확인됐다. 법령 grounding은 현재 로컬
ChromaDB 기준 사용 가능한 상태다.
