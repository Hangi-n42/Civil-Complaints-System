# 법령 조문 인덱스 반영 후 QA E2E 재검증

작성일: 2026-06-09  
담당: BE2 검색  
관련 이슈: #348

## 1. 목적

`law_articles_v1` 법령 조문 인덱스가 정상 저장된 이후, 실제 QA 흐름에서
BE1 구조화 신호, BE2 검색, grounding filter, BE3 답변 생성, 법령 grounding 상태가
함께 동작하는지 재검증한다.

민원 원문, 검색 snippet, 생성 답변 미리보기 등 개인정보 위험이 있는 raw 결과는
커밋하지 않고 `/tmp`에만 저장했다.

- `/tmp/law_grounding_e2e_raw_10.json`
- `/tmp/law_grounding_e2e_raw_10.md`

## 2. 실행 조건

```bash
STRUCTURING_CONSTRAINED=true python scripts/e2e_be1_query_signals_search_qa.py \
  --structuring-mode actual \
  --grounding-filter \
  --run-generation \
  --limit 10 \
  --top-k 5 \
  --out-json /tmp/law_grounding_e2e_raw_10.json \
  --out-md /tmp/law_grounding_e2e_raw_10.md
```

추가로 citation 노출 정책을 직접 확인했다.

```bash
python - <<'PY'
from app.retrieval.law_article_store import get_law_article_store
from app.generation.citation.legal_citation import ground_legal_citations

store = get_law_article_store()
articles = store.search(
    "무허가 가설건축물 이행강제금",
    law_ids=["001823"],
    key_terms=["이행강제금"],
    top_k=3,
)
result = ground_legal_citations(
    "건축법 제80조에 따라 검토합니다. 건축법 제999조도 검토합니다.",
    articles,
)
PY
```

## 3. 핵심 결과

| 항목 | 결과 |
| --- | ---: |
| 샘플 수 | 10 |
| 정상 처리 | 10 |
| 실패 | 0 |
| baseline 빈 결과 | 0 |
| query_signals 적용 후 빈 결과 | 0 |
| grounding filter 실행 | 10 |
| grounding filter 오류 | 0 |
| 답변 생성 실행 | 10 |
| 답변 생성 오류 | 0 |
| 빈 답변 | 0 |
| fallback 사용 | 3 |
| 최대 JSON 파싱 재시도 | 3 |

## 4. BE1 신호 커버리지

| 신호 | 값이 나온 샘플 수 |
| --- | ---: |
| `entity_texts` | 4 |
| `legal_ref_names` | 3 |
| `legal_ref_ids` | 3 |
| `issue_types` | 6 |
| `key_terms` | 6 |
| `responsible_units` | 0 |

## 5. 검색 및 rerank 관측

| 항목 | 결과 |
| --- | ---: |
| top1 변경 | 1 |
| 기존 top-k 안에서 위로 올라간 후보 | 4 |
| query_signals와 metadata overlap이 있는 후보가 top1인 건수 | 6 |

metadata soft rerank는 결과를 비우지 않았고, grounding filter도 오류 없이 실행됐다.

## 6. 답변 생성 및 법령 grounding 관측

generation mode:

| mode | 건수 |
| --- | ---: |
| `default` | 7 |
| `fast_fallback` | 3 |

legal grounding status:

| status | 건수 |
| --- | ---: |
| `no_candidates` | 7 |
| `grounded` | 3 |

법령 grounding이 적용된 3건은 모두 `fast_fallback`으로 생성됐다.
빈 답변은 없었지만, 법령 grounding이 붙은 케이스에서 로컬 생성 모델이 JSON 계약을
안정적으로 맞추지 못하는 리스크는 남아 있다.

이전 BE2 최종 QA E2E와 비교하면 `force_json` 1건이 없어지고 `default`가 7건으로
늘었다. 다만 `fast_fallback` 3건과 법령 grounding 3건의 결합은 유지됐다.

## 7. citation 노출 정책 확인

직접 citation 검증 결과:

| 항목 | 결과 |
| --- | ---: |
| 검색 조문 수 | 3 |
| valid citation | 1 |
| invalid citation | 1 |
| warning | 1 |
| valid citation `public_url` 포함 | 예 |
| valid citation `source_url` 포함 | 아니오 |
| invalid citation `source_url` 포함 | 아니오 |

확인된 valid citation 필드:

| 필드 |
| --- |
| `article_no` |
| `doc_type` |
| `law_id` |
| `law_name` |
| `public_url` |
| `raw` |
| `verified` |

따라서 citation 검증 경로에서는 내부 `source_url`이 제거되고, 공개용 `public_url`만
남는 것을 확인했다.

## 8. 결론

법령 조문 인덱스 반영 후 QA E2E는 BE2 검색 관점에서 통과했다.

- 검색 빈 결과 없음
- grounding filter 오류 없음
- 답변 생성 오류 없음
- 빈 답변 없음
- 법령 grounding 상태 관측 가능
- citation 검증 경로에서 `source_url` 제거 및 `public_url` 유지 확인

남은 리스크:

- 법령 grounding이 적용된 3건은 모두 `fast_fallback`이었다.
- 이는 BE2 검색 실패라기보다 BE3 생성 JSON 안정성 후속 개선 후보로 본다.
- `responsible_units`는 이번 샘플에서도 0건이라 담당부서 신호는 여전히 실제 E2E sample에서 검증되지 않았다.

운영 판단:

BE2 검색과 법령 조문 검색 연결은 현재 사용 가능한 상태다. 운영 전에는 BE3에서
`generation_mode=fast_fallback`과 `legal_grounding_status=grounded`가 함께 발생하는
비율을 모니터링해야 한다.
