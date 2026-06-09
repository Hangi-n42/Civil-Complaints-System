# BE2 검색 readiness 운영 스모크 체크 리포트

- 생성 시각(UTC): `2026-06-09T07:30:41.690547+00:00`
- 관련 이슈: #352
- 전체 결과: **통과**
- 상세 산출물 위치: `/tmp/be2_operational_smoke_check`

## 확인 항목

| 항목 | 결과 | 실행 명령/검증 | 비고 |
| --- | --- | --- | --- |
| ChromaDB 검색 신호 metadata 적재율 | 통과 | `python scripts/check_chromadb_search_signal_coverage.py --persist-dir data/chroma_db --collection civil_cases_v1 --limit 0 --out-json /tmp/be2_operational_smoke_check/chromadb_search_signal_metadata_coverage.json --out-md /tmp/be2_operational_smoke_check/chromadb_search_signal_metadata_coverage.md` | 민감 필드는 해시 처리, 상세 리포트는 /tmp/be2_operational_smoke_check에 저장 |
| 법령 조문 인덱스 | 통과 | `python scripts/check_law_index.py` | `law_articles_v1` 대표 질의 검색과 인용검증 확인 |
| citation 공개 URL 정책 | 통과 | `ground_legal_citations() fixture assert` | valid citation은 public_url만 포함하고 source_url은 제거됨 |

## 운영 판단 기준

- ChromaDB `civil_cases_v1`의 검색 신호 metadata 적재율을 확인한다.
- 법령 조문 collection `law_articles_v1`가 존재하고 대표 질의 검색/인용검증이 통과해야 한다.
- 공개 응답 citation에는 `source_url`을 노출하지 않고 `public_url`만 남아야 한다.
- 민원 원문, 검색 snippet, 생성 답변 미리보기 등 개인정보 위험 raw 산출물은 커밋하지 않는다.

## 남은 리스크 확인

- `entity_texts` 적재율이 낮으면 객체명 기반 rerank 효과는 제한적으로 해석한다.
- `responsible_units`는 fallback 값일 수 있으므로 확정 담당부서처럼 해석하지 않는다.
- 법령 grounding 이후 `fast_fallback` 증가는 BE3 생성 안정성 이슈로 분리해 본다.
