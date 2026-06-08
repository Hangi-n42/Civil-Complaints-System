# BE2 검색 최종 완료 리포트

작성일: 2026-06-09  
담당: BE2 검색  
기준 커밋: `534e871 [BE2] BE3 handoff 기준 최종 QA E2E 검증 (#332) (#333)`

## 1. 목적

BE2 검색 파트의 최종 완료 상태를 정리한다. 이 문서는 기능 상세 설계보다
후속 인수인계에 초점을 둔다.

- 완료된 검색 범위
- 최종 E2E 검증 결과
- 남은 리스크
- BE1, BE3, FE에 전달할 메시지
- 운영 전 체크리스트

민원 원문, 검색 snippet, 생성 답변 미리보기처럼 개인정보 위험이 있는 raw 산출물은
이 문서에 포함하지 않는다.

## 2. 완료 범위

BE2 검색은 BE1 구조화 신호를 받아 검색 랭킹에 반영하고, BE3 답변 생성까지 이어지는
경로에서 필요한 검색 컨텍스트와 라우팅 정보를 전달하는 수준까지 완료했다.

완료된 핵심 범위:

| 범위 | 상태 | 비고 |
| --- | --- | --- |
| BE1 `query_signals` metadata 저장 | 완료 | `entity_texts`, `legal_ref_names`, `legal_ref_ids`, `issue_types`, `key_terms`, `responsible_units`, `urgency_level` |
| metadata 기반 soft rerank | 완료 | hard filter가 아니라 가점 기반 보정 |
| ChromaDB 기존 metadata backfill 검증 | 완료 | 과거 collection의 신규 metadata 누락 가능성 보완 |
| 실제 BE1 구조화 신호 기반 검색 E2E | 완료 | 실제 `query_signals` 경로 확인 |
| BE3 grounding filter 연계 | 완료 | 검색 결과 재사용 QA 경로 포함 |
| BE3 generation metadata 관측 | 완료 | fallback, legal grounding status 확인 가능 |
| BE3 빈 answer 방어 확인 | 완료 | 최종 sample 10에서 빈 답변 0건 |

관련 완료 PR:

| PR | 내용 |
| --- | --- |
| #318 | BE1 검색 신호 metadata 저장 |
| #319 | BE1 metadata 기반 soft rerank 적용 |
| #320 | metadata soft rerank 평가 및 ChromaDB LFS 정책 |
| #324 | 실제 BE1 `query_signals` 검색 E2E 검증 |
| #327 | BE3 generation metadata E2E 리포트 반영 |
| #330 | BE3 빈 answer 방어 및 generation/legal signal handoff 보강 |
| #333 | BE3 handoff 기준 BE2 최종 QA E2E 검증 |

## 3. 최종 E2E 검증 결과

최종 검증 산출물:

- `reports/retrieval/v3/be3_handoff_e2e_summary.md`
- `reports/retrieval/v3/be3_handoff_e2e_summary.json`

검증 명령:

```bash
STRUCTURING_CONSTRAINED=true python scripts/e2e_be1_query_signals_search_qa.py \
  --structuring-mode actual \
  --grounding-filter \
  --run-generation \
  --limit 10 \
  --top-k 5 \
  --out-json /tmp/be3_handoff_e2e_raw_10_with_legal.json \
  --out-md /tmp/be3_handoff_e2e_raw_10_with_legal.md
```

핵심 결과:

| 항목 | 결과 |
| --- | ---: |
| 샘플 수 | 10 |
| 정상 처리 | 10 |
| 검색 빈 결과 | 0 |
| grounding filter 오류 | 0 |
| 답변 생성 오류 | 0 |
| 빈 답변 | 0 |
| fallback 사용 | 3 |

generation mode:

| mode | 건수 |
| --- | ---: |
| `default` | 6 |
| `force_json` | 1 |
| `fast_fallback` | 3 |

legal grounding status:

| status | 건수 |
| --- | ---: |
| `no_candidates` | 7 |
| `grounded` | 3 |

BE1 신호 커버리지:

| 신호 | 값이 나온 샘플 수 |
| --- | ---: |
| `entity_texts` | 4 |
| `legal_ref_names` | 3 |
| `legal_ref_ids` | 3 |
| `issue_types` | 6 |
| `key_terms` | 6 |
| `responsible_units` | 0 |

검색 관측:

| 항목 | 결과 |
| --- | ---: |
| top1 변경 | 1 |
| 기존 top-k 안에서 위로 올라간 후보 | 4 |
| `query_signals`와 metadata overlap이 있는 후보가 top1인 건수 | 6 |

결론:

- BE1 구조화 신호가 BE2 검색 경로까지 전달된다.
- metadata soft rerank는 검색 결과를 비우지 않는다.
- grounding filter는 최종 sample 10에서 오류 없이 실행됐다.
- BE3 답변 생성까지 연결했을 때 빈 답변은 재현되지 않았다.
- 법령 grounding 상태는 `generation_metadata.legal_grounding_status`로 확인할 수 있다.

## 4. 남은 리스크

### 4.1 법령 grounding + `fast_fallback`

법령 grounding이 적용된 3건은 모두 `fast_fallback`으로 생성됐다.
빈 답변은 아니지만, 법령 grounding이 붙은 질의에서 생성 모델이 JSON 계약을 안정적으로
맞추지 못하는 경향이 있다.

판단:

- BE2 검색 실패로 보지는 않는다.
- BE3 생성 JSON 안정화 후속 개선 후보로 남긴다.
- 운영 전에는 `generation_metadata.generation_mode`와
  `generation_metadata.legal_grounding_status`를 함께 모니터링해야 한다.

### 4.2 `responsible_units` 커버리지 0건

최종 sample 10에서는 `responsible_units`가 한 번도 채워지지 않았다.

판단:

- 담당부서 신호 기반 rerank는 이번 최종 sample에서는 검증되지 않았다.
- BE1 책임부서 후보 기능이 기본 비활성 상태이거나, sample 특성상 낮은 커버리지였을 수 있다.
- 운영 전에는 실제 운영 설정에서 책임부서 후보 적재율과 검색 영향도를 별도로 확인해야 한다.

### 4.3 과거 인덱스 metadata 누락 가능성

기존 Chroma collection에는 신규 metadata가 없을 수 있다.

판단:

- 신규 인덱싱 데이터는 검색 신호를 metadata로 유지해야 한다.
- 과거 collection을 그대로 쓸 경우 backfill 후 필드 적재율을 확인해야 한다.

## 5. 팀별 전달사항

### BE1에 전달

- 구조화 입력은 상담사 답변이 아니라 민원인 원문 기준이어야 한다.
- `legal_refs`, `responsible_unit`은 확정값이 아니라 검색 보조 후보로 유지한다.
- `confidence`는 미보정 휴리스틱이므로 BE2/BE3에서 hard filter나 확정 확률로 쓰지 않는다.
- `legal_ref_ids`와 `legal_ref_names`는 가능하면 같은 항목 순서를 유지한다.
- 운영 전 책임부서 후보 기능 설정과 적재율을 확인한다.

### BE2에 전달

- `query_signals`는 hard filter가 아니라 soft rerank 신호로만 사용한다.
- 검색 이후 `routing_hint`, `routing_trace`, `route_key`, `strategy_id`를 임의로 재계산하지 않는다.
- `/search` 경로와 검색 결과 재사용 `/qa` 경로 모두 metadata soft rerank 후 grounding filter 흐름을 유지한다.
- grounding filter 결과가 0개인 경우 사용자용 `/qa`는 근거 없음 fallback을 반환해야 한다.
- 신규 metadata가 없는 collection을 운영에 쓰지 않도록 backfill 또는 재인덱싱 상태를 확인한다.

### BE3에 전달

- 법령 grounding이 붙은 케이스에서 `fast_fallback`이 발생하는 경향이 관측됐다.
- 빈 답변 방어는 최종 sample 10에서 통과했지만, JSON 계약 안정성은 후속 개선 후보다.
- `generation_metadata.generation_mode`, `generation_metadata.legal_grounding_status`,
  `legal_citation_warnings`를 운영 모니터링에 포함한다.
- 검증되지 않은 법령 인용, 부서명, 전화번호, 처리기한을 생성하지 않는 정책을 유지한다.

### FE에 전달

- `/search` 응답의 `routing_hint`를 같은 민원의 `/qa` 요청에 그대로 전달해야 한다.
- 가능한 경우 `/search`에서 사용한 `query_signals`도 `/qa`에 함께 전달한다.
- 다른 민원을 선택하면 이전 민원의 `routing_hint`를 재사용하지 않는다.
- `generation_metadata`와 `legal_citation_warnings`를 숨기지 말고 검토자에게 노출할 수 있어야 한다.
- 법령 링크는 공개용 `public_url`만 사용하고 내부 URL이나 원천 키는 표시하지 않는다.

## 6. 운영 전 체크리스트

| 항목 | 확인 |
| --- | --- |
| main 최신 배포 기준 커밋 확인 | `534e871` 또는 그 이후 |
| Chroma collection 신규 metadata 적재율 확인 | `query_signals` 관련 필드 |
| 과거 collection 사용 시 backfill 완료 확인 | `scripts/backfill_chromadb_search_signals.py` |
| 법령 인덱스 상태 확인 | `python scripts/check_law_index.py` |
| 책임부서 후보 기능 설정 확인 | `ENABLE_RESPONSIBLE_UNIT` 및 인덱스 |
| `/search` -> `/qa` `routing_hint` 전달 확인 | 동일 민원 기준 |
| grounding filter 0건 fallback 확인 | 가짜 답변 생성 금지 |
| `fast_fallback` 비율 모니터링 | 법령 grounding 케이스 포함 |
| 개인정보 raw 산출물 커밋 방지 | 민원 원문, snippet, 답변 미리보기 제외 |

## 7. 완료 판단

BE2 검색 파트는 BE1 구조화 신호 기반 검색 보정, grounding filter 연계, BE3 QA 생성
handoff 기준 E2E 검증까지 완료했다.

남은 항목은 BE2 검색 기능의 미완료라기보다 운영 전 확인과 BE3 생성 안정화 후속 개선에
가깝다. 따라서 현재 기준에서 BE2 검색은 handoff 가능한 상태로 판단한다.
