# BE1 최신 구조화 기반 원천 데이터 10건 파일럿 결과

- 작성일: 2026-06-10
- 작업 이슈: #365
- 기준 브랜치: `codex/be2-be1-restructured-index-365`
- 기준 데이터: `data/Public_Civil_Service_LLM_Data`의 Training + Validation 원천 데이터
- 대상 컬렉션: `civil_cases_be1_source_pilot10`

## 입력 데이터 확인

원천 데이터는 Training과 Validation의 `01.원천데이터`를 합쳐 총 9,132건이다. 현재 운영 검색 말뭉치 `data/evaluation/v3/corpus_meta.json` 및 `civil_cases_v1` 컬렉션도 9,132건이라 전체 건수와 source_id 기준이 일치한다.

구조화 입력은 BE1 핸드오프 계약에 맞춰 상담사 답변을 제외했다.

| 입력 유형 | 건수 |
| --- | ---: |
| `title + Q` | 8,186 |
| 고객/민원인 발화 | 946 |
| fallback 전체 본문 | 0 |
| 빈 입력 | 0 |

## 10건 파일럿 실행

실행 명령:

```bash
ENABLE_RESPONSIBLE_UNIT=true RESPONSIBLE_UNIT_USE_LLM=false \
python3 scripts/rebuild_be1_restructured_index.py \
  --input-mode public-source \
  --limit 10 \
  --collection-name civil_cases_be1_source_pilot10 \
  --batch-size 5 \
  --output-jsonl /tmp/be1_source_pilot10.jsonl \
  --failures-jsonl /tmp/be1_source_pilot10_failures.jsonl
```

결과:

| 항목 | 값 |
| --- | ---: |
| 처리 건수 | 10 |
| 실패 건수 | 0 |
| Chroma 적재 건수 | 10 |
| 소요 시간 | 76.43초 |
| 로컬 전체 예상 시간 | 약 19.4시간 |

기존 `civil_cases_v1` 9,132건은 변경하지 않았고, 파일럿 전용 새 컬렉션만 생성했다.

## Metadata 적재율

점검 명령:

```bash
python3 scripts/check_chromadb_search_signal_coverage.py \
  --persist-dir data/chroma_db \
  --collection civil_cases_be1_source_pilot10
```

| 필드 | 적재 건수 | 적재율 |
| --- | ---: | ---: |
| `entity_texts` | 10 / 10 | 100.00% |
| `legal_ref_names` | 0 / 10 | 0.00% |
| `legal_ref_ids` | 0 / 10 | 0.00% |
| `issue_types` | 8 / 10 | 80.00% |
| `key_terms` | 10 / 10 | 100.00% |
| `responsible_units` | 10 / 10 | 100.00% |
| `responsible_units_source` | 10 / 10 | 100.00% |
| `urgency_level` | 10 / 10 | 100.00% |

첫 10건이 모두 국립아시아문화전당의 공연/예매/투어 문의라 법령 후보가 없는 것은 자연스러운 결과다. `responsible_units_source`는 모두 `be1_structured`로 보존됐다.

## 검색 Smoke 결과

원문과 snippet은 기록하지 않고 질의별 1위 결과만 남긴다.

| 질의 | 1위 case_id | 확인된 metadata 신호 |
| --- | --- | --- |
| 공연 예매 취소가 안 됩니다 | `CASE-002470` | `entity_texts`, `issue_types`, `responsible_units_source` |
| 단체 관람 콘서트 티켓 예매 문의 | `CASE-000012` | `entity_texts`, `issue_types`, `responsible_units_source` |
| 도슨트 가이드 프로그램 문의 | `CASE-002471` | `entity_texts`, `issue_types`, `responsible_units_source` |

## 판단

원천 데이터 기준 10건 파일럿은 통과했다. 다만 로컬 전체 실행 예상 시간이 약 19.4시간이므로, 전체 9,132건 재구조화는 로컬 노트북이 아닌 고성능 실행 환경에서 진행하는 것이 맞다. 전체 실행은 해당 실행 환경 준비가 끝난 뒤 진행한다.
