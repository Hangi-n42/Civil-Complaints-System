# BE1 query_signals 검색 E2E 검증

작성일: 2026-06-08
담당: BE2

## 목적

BE1이 만든 신규 검색 신호가 BE2 검색에 실제로 들어가서 순위에 영향을 주는지 확인한다.
이 문서는 운영 로직 변경이 아니라 검증 방법을 설명한다.

확인하려는 흐름은 다음과 같다.

1. 전처리 민원 1건을 BE1 구조화 입력으로 바꾼다.
2. BE1 구조화 결과에서 `query_signals`를 만든다.
3. BE2 Hybrid 검색을 두 번 실행한다.
   - baseline: `query_signals` 없음
   - 실험군: `query_signals` 있음
4. top-k 순위 변화와 후보 metadata overlap을 기록한다.
5. 필요하면 grounding filter와 답변 생성까지 이어서 확인한다.

## 스크립트

```bash
python scripts/e2e_be1_query_signals_search_qa.py \
  --limit 10 \
  --structuring-mode deterministic \
  --out-json /tmp/be1_query_signals_e2e.json \
  --out-md /tmp/be1_query_signals_e2e_summary.md
```

`deterministic` 모드는 LLM 4요소 추출을 건너뛰고 BE1의 검색 신호 함수만 실행한다.
로컬 smoke test에 적합하다.

실제 BE1 구조화까지 포함하려면 아래처럼 실행한다.

```bash
python scripts/e2e_be1_query_signals_search_qa.py \
  --limit 20 \
  --structuring-mode actual \
  --grounding-filter \
  --out-json reports/retrieval/v3/be1_query_signals_e2e.json \
  --out-md reports/retrieval/v3/be1_query_signals_e2e_summary.md
```

답변 생성까지 확인하려면 Ollama 생성 모델이 준비된 환경에서 `--run-generation`을 추가한다.

```bash
python scripts/e2e_be1_query_signals_search_qa.py \
  --limit 5 \
  --structuring-mode actual \
  --grounding-filter \
  --run-generation
```

`--run-generation`을 켜면 BE3가 반환한 `generation_metadata`도 함께 기록한다.
이 값은 검색 품질 점수가 아니라 답변 생성 단계의 상태 표시등이다.

| 필드 | 의미 |
| --- | --- |
| `fallback_used` | BE3가 fast fallback 또는 no-evidence fallback을 사용했는지 |
| `parse_retry_count` | QA JSON 파싱 실패 후 재시도한 횟수 |
| `generation_mode` | 최종 생성 모드(`default`, `force_json`, `compact`, `fast_fallback`, `no_evidence_fallback`) |

답변 본문이 비어 있으면 `empty_answer` 경고로 표시한다.
이 경우 BE2 검색은 성공했더라도 답변 초안 생성 검증은 실패 또는 재확인 대상으로 본다.

## 실행 위치

무거운 실행은 Tailscale로 접속한 데스크톱에서 수행한다.

- `--structuring-mode actual`: BE1 구조화 LLM 호출 가능성이 있다.
- `--grounding-filter`: LLM relevance filter 호출 가능성이 있다.
- `--run-generation`: 답변 생성 LLM 호출이 필요하다.
- ChromaDB와 embedding runtime이 준비된 환경에서 실행해야 한다.

## 결과 해석

리포트에서 가장 먼저 볼 숫자는 다음이다.

| 항목 | 의미 |
| --- | --- |
| `signal_coverage` | BE1 신호가 실제로 얼마나 생성됐는지 |
| `top1_changed_count` | metadata rerank로 1등 후보가 바뀐 샘플 수 |
| `moved_up_candidate_count` | 기존 후보 중 신호 일치로 위로 올라간 후보 수 |
| `with_signals_top1_has_metadata_overlap_count` | 1등 후보가 query_signals와 실제 metadata를 공유하는 샘플 수 |
| `with_signals_empty_count` | 신호 적용 후 빈 결과가 생겼는지 |
| `grounding_error_count` | grounding filter 실행 중 오류가 있었는지 |
| `generation_warning_count` | 답변 생성 결과에 경고가 있는지 |
| `generation_empty_answer_count` | 답변 본문이 비어 있는지 |
| `generation_fallback_count` | BE3 fallback 응답이 사용됐는지 |
| `generation_mode_counts` | 답변 생성 모드별 분포 |

좋은 결과는 “빈 결과는 늘지 않고, metadata overlap이 있는 후보가 조금 더 위로 올라가는 것”이다.
반대로 top1이 자주 바뀌는데 overlap 근거가 약하면 boost가 검색을 흔드는지 확인해야 한다.

답변 생성까지 실행한 경우에는 검색 결과와 답변 생성 결과를 분리해서 해석한다.
검색 결과가 정상이어도 `empty_answer`나 `fallback_used`가 나오면 BE3 생성 품질 또는 QA 계약 문제로 별도 확인한다.

## 주의

이 검증은 정답셋 평가가 아니다. 즉, 순위가 바뀌었다고 바로 성능이 좋아졌다고 말할 수는 없다.
다만 실제 운영 입력에서 BE1 신호가 비어 있는지, BE2가 그 신호를 받아 순위를 바꾸는지,
답변 초안 검색 전에 문제가 생기는지 빠르게 확인할 수 있다.

민원 원문과 검색 snippet이 리포트에 포함될 수 있으므로 개인정보 검토 전에는 기본 리포트를 커밋하지 않는다.
