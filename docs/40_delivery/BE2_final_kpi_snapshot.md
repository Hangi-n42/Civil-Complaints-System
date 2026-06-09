# BE2 최종 검색 KPI 스냅샷

작성일: 2026-06-09
담당: BE2 검색
관련 이슈: #356

## 1. 목적

BE2 검색 파트의 최종 목표 대비 현재 달성 상태를 발표와 최종보고서에 바로 사용할 수
있도록 한 장으로 정리한다.

이 문서는 새로운 검색 로직을 제안하지 않는다. 이미 main에 반영된 평가, E2E, readiness,
completion gate 산출물을 요약한다.

민원 원문, 검색 snippet, 생성 답변 미리보기 등 개인정보 위험이 있는 raw 내용은 포함하지
않는다.

## 2. 한 줄 결론

BE2 검색은 현재 기준으로 **기능 완료 및 handoff 가능** 상태다.

운영 관점에서는 `entity_texts` 낮은 적재율, `responsible_units` fallback 가능성,
BE3 법령 grounding `fast_fallback`을 모니터링하는 조건으로 **조건부 통과**로 본다.

## 3. 최종 KPI

| 영역 | 지표 | 현재값 | 판단 | 출처 |
| --- | --- | ---: | --- | --- |
| 일반 검색 품질 | Hybrid `nDCG@5` | 0.752 | 통과 | `docs/20_domains/retrieval/eval_overhaul_summary.md` |
| 일반 검색 품질 | Hybrid `P@5` | 0.766 | 통과 | `docs/20_domains/retrieval/eval_overhaul_summary.md` |
| 일반 검색 품질 | Hybrid `RR@5` | 0.876 | 통과 | `docs/20_domains/retrieval/eval_overhaul_summary.md` |
| metadata rerank | Hybrid+metadata `nDCG@5` | 0.7542 | 통과 | `reports/retrieval/v3/metadata_soft_rerank_summary.md` |
| metadata rerank | Hybrid+metadata `nDCG@10` | 0.7428 | 통과 | `reports/retrieval/v3/metadata_soft_rerank_summary.md` |
| metadata rerank | Hybrid+metadata `R@10` | 0.3172 | 통과 | `reports/retrieval/v3/metadata_soft_rerank_summary.md` |
| 엉뚱한 근거 제거 | 원본 Hybrid rel0 비율 | 23.20% | 기준선 | `reports/retrieval/v3/grounding_filter_completion_check.md` |
| 엉뚱한 근거 제거 | 필터 후 rel0 비율 | 4.17% | 통과 | `reports/retrieval/v3/grounding_filter_completion_check.md` |
| 엉뚱한 근거 제거 | rel0 상대 감소율 | 82.03% | 통과 | `reports/retrieval/v3/grounding_filter_completion_check.md` |
| 엉뚱한 근거 제거 | 필터 후 유효 근거 비율 | 95.83% | 통과 | `reports/retrieval/v3/grounding_filter_completion_check.md` |
| 엉뚱한 근거 제거 | rel0가 남은 쿼리 비율 | 14.00% | 통과 | `reports/retrieval/v3/grounding_filter_completion_check.md` |
| E2E 안정성 | 최종 E2E 검색 빈 결과 | 0건 | 통과 | `reports/retrieval/v3/be3_handoff_e2e_summary.json` |
| E2E 안정성 | 최종 E2E grounding 오류 | 0건 | 통과 | `reports/retrieval/v3/be3_handoff_e2e_summary.json` |
| E2E 안정성 | 최종 E2E 답변 생성 오류 | 0건 | 통과 | `reports/retrieval/v3/be3_handoff_e2e_summary.json` |
| E2E 안정성 | 최종 E2E 빈 답변 | 0건 | 통과 | `reports/retrieval/v3/be3_handoff_e2e_summary.json` |
| 운영 readiness | BE2 operational smoke check | 통과 | 통과 | `reports/retrieval/v3/be2_operational_smoke_check.md` |

## 4. 완료로 볼 수 있는 항목

| 항목 | 상태 | 근거 |
| --- | --- | --- |
| Hybrid 검색 기본 전략 | 완료 | 교정 평가셋에서 Hybrid가 주요 상위권 지표 1위 |
| BE1 query_signals metadata 저장 | 완료 | Chroma metadata 저장/복원 및 API 노출 완료 |
| metadata soft rerank | 완료 | hard filter 없이 소폭 개선, 빈 결과 없음 |
| grounding filter | 완료 | rel0 23.20% -> 4.17%, completion gate 통과 |
| `/search -> /qa` handoff | 완료 | routing/query signal/grounding filter E2E 확인 |
| 법령 조문 인덱스 연결 | 완료 | `law_articles_v1` 17,759건 및 citation 검증 확인 |
| 운영 스모크 체크 | 완료 | 한 명령으로 readiness 재현 가능 |

## 5. BE2 미완료가 아닌 후속 리스크

| 리스크 | 현재 판단 | 담당/후속 |
| --- | --- | --- |
| `entity_texts` 적재율 11.03% | 객체명 기반 rerank 효과 제한 | BE1 entities 고도화 #308 |
| `responsible_units` 100% 적재 | 실제 담당부서 후보가 아니라 category/source fallback 가능성 | BE1/BE2 신규 metadata 출처 구분 |
| 법령 grounding 3건 모두 `fast_fallback` | 검색 실패가 아니라 생성 JSON 안정성 이슈 | BE3 #350 |
| 필터 결과 0건 쿼리 7% | 검색 실패가 아니라 안전 fallback 대상 | `/qa` `no_evidence_fallback` 유지 |

## 6. 발표용 요약 문장

BE2는 단순히 유사 사례를 많이 찾는 것보다, 답변 생성에 위험한 엉뚱한 근거를 줄이는
방향으로 평가 기준을 정리했다.

최종 검색 스택은 Hybrid 기반이며, grounding filter 적용 후 엉뚱한 근거(rel0) 비율을
23.20%에서 4.17%로 낮췄다. BE1 구조화 신호 기반 soft rerank와 BE3 QA handoff도
연결됐고, 최종 E2E에서 검색 빈 결과, grounding 오류, 답변 생성 오류, 빈 답변은 모두
0건이었다.

따라서 BE2 검색은 현재 기능 완료 및 handoff 가능한 상태이며, 남은 리스크는 BE1 신호
커버리지 개선과 BE3 법령 grounding 생성 안정성으로 분리해 관리한다.

## 7. 재현 명령

```bash
python scripts/check_grounding_filter_completion.py
python scripts/check_be2_operational_readiness.py
python scripts/check_law_index.py
```

관련 단위 테스트:

```bash
python -m pytest app/tests/unit/test_grounding_filter.py app/tests/unit/test_generation_week5_contract.py -q
```
