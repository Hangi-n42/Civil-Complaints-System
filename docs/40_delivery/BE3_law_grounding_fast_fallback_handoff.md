# BE3 핸드오프 — 법령 grounding 케이스 fast_fallback 안정화 요청

작성일: 2026-06-09  
작성: BE2 검색  
관련 이슈: #350  
근거 리포트: `reports/retrieval/v3/law_grounding_qa_e2e_recheck.md`

## 1. 목적

`law_articles_v1` 법령 조문 인덱스 반영 이후 QA E2E를 재검증한 결과,
BE2 검색과 법령 조문 검색, citation 검증 경로는 정상으로 확인됐다.

다만 법령 grounding이 적용된 3건이 모두 `fast_fallback`으로 생성됐다.
이 문서는 BE3가 이미 완료한 빈 답변 방어와 생성 metadata 전달 작업을 중복 요청하지 않고,
그 이후에도 남은 법령 grounding 케이스의 후속 품질 개선 지점을 정리한다.

민원 원문, 검색 snippet, 생성 답변 미리보기 등 개인정보 위험이 있는 raw 결과는
공유하지 않는다.

## 2. 재현 조건

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

raw 결과는 `/tmp`에만 저장했고 커밋하지 않았다.

## 3. BE3 기존 완료 범위와 이번 요청의 차이

GitHub issue, issue comment, PR 기록 기준으로 BE3가 이미 완료한 범위는 아래와 같다.

| 범위 | 관련 기록 | 판단 |
| --- | --- | --- |
| 민원 회신문 1~4항 형식 안정화, 출처 토큰 위치 고정, Q0~Q8 평가 체계 | #295, #297 | 완료된 BE3 범위 |
| 빈 `answer`를 정상 성공으로 처리하지 않는 방어 | #328, #330 | 완료된 BE3 범위 |
| 공백 답변 발생 시 재시도 후 `fast_fallback` 적용 | #328, #330 | 완료된 BE3 범위 |
| `fallback_used`, `generation_mode`, `parse_retry_count` 등 생성 metadata 전달 | #325, #330, #331 | 완료된 BE3 범위 |
| 법령 인용 신호와 fallback metadata를 API/서비스/UI 흐름에 보존 | #330, #331 | 완료된 BE3 범위 |
| BE3 integration checklist 완료 표시 | #344 | 완료된 BE3 범위 |

따라서 이번 요청은 "BE3가 빈 답변 방어를 하지 않았다"는 의미가 아니다.

이번에 BE2가 남기는 후속 확인 지점은 다음 하나다.

> #330 이후에도 법령 grounding이 실제 적용된 케이스가 모두 `fast_fallback`으로 관측되므로,
> 법령 조문 컨텍스트가 포함된 생성에서 fallback 없이 JSON 응답 계약을 안정적으로 지킬 수 있는지 확인한다.

## 4. E2E 요약

| 항목 | 결과 |
| --- | ---: |
| 샘플 수 | 10 |
| 정상 처리 | 10 |
| 실패 | 0 |
| 검색 빈 결과 | 0 |
| grounding filter 오류 | 0 |
| 답변 생성 오류 | 0 |
| 빈 답변 | 0 |
| fallback 사용 | 3 |
| 최대 JSON 파싱 재시도 | 3 |

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

핵심 관측:

- `legal_grounding_status=grounded` 3건은 모두 `generation_mode=fast_fallback`이었다.
- 빈 답변은 0건이었다.
- 답변 생성 오류는 0건이었다.
- fallback 방어는 작동했지만, 법령 grounding 케이스에서 JSON 계약 안정성은 부족했다.

## 5. BE2에서 확인 완료한 범위

BE2 검색/법령 검색 관점에서는 아래를 확인했다.

| 확인 항목 | 결과 |
| --- | --- |
| `law_articles_v1` collection 존재 | 확인 |
| 법령 조문 색인 수 | 17,759건 |
| `law_id`, `law_name`, `article_no` metadata | 전 건 적재 |
| 법령 필터 검색 | 정상 |
| BE1 `legal_ref_ids` 기반 조문 검색 | 동작 |
| grounding filter | 오류 없음 |
| citation 검증 경로 | 동작 |
| `source_url` 공개 응답 제거 | 확인 |
| `public_url` 유지 | 확인 |

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

따라서 현재 이슈는 BE2 검색 실패라기보다, 법령 컨텍스트가 포함된 BE3 생성 응답이
기존 fallback 방어까지 도달하는 비율을 낮출 수 있는지 확인하는 후속 품질 리스크에 가깝다.

## 6. BE3 확인 요청

### 6.1 JSON 응답 계약 안정성

법령 grounding 케이스에서 다음 현상이 반복됐다.

- strict JSON 파싱 실패
- 완화 파싱 실패
- 최대 3회 재시도
- `fast_fallback` 진입

BE3에서 확인할 지점:

- 법령 조문 컨텍스트가 프롬프트에 들어갈 때 JSON 출력 지시가 약해지는지
- `[법령 조문]` 블록이 길거나 법령 문장이 복잡할 때 모델이 설명문으로 이탈하는지
- `answer`, `citations`, `limitations` 필드 누락이 왜 반복되는지
- `force_json` 또는 더 강한 JSON schema 유도 전략이 필요한지

### 6.2 법령 컨텍스트와 fallback 진입 조건

현재 fallback은 빈 답변 방어 측면에서는 안전하게 작동한다.
하지만 법령 grounding 케이스가 모두 fallback으로 빠지면, 조문 기반 답변 품질을
확인하기 어렵다.

BE3에서 확인할 지점:

- `legal_grounding_status=grounded`일 때 fallback 진입 전 최소 JSON 복구가 가능한지
- 법령 컨텍스트 포함 시 `temperature=0.0` 재시도만으로 충분한지
- 법령 인용 지시와 일반 RAG 지시가 충돌하지 않는지
- fallback 답변에도 법령 grounding metadata를 어떻게 표현할지

### 6.3 응답 metadata 모니터링

운영 모니터링에서는 아래 조합을 우선 추적하는 것을 권장한다.

| 지표 | 해석 |
| --- | --- |
| `generation_mode=fast_fallback` + `legal_grounding_status=grounded` | 법령 컨텍스트 포함 생성 안정성 리스크 |
| `parse_retry_count=3` | JSON 계약 복구 실패 |
| `legal_citations=[]` + `legal_grounding_status=grounded` | 조문 검색은 됐지만 답변 인용이 없거나 fallback 가능 |
| `legal_citation_warnings` 존재 | 미검증 조문 인용 제거 발생 |

## 7. BE2가 유지할 정책

BE2는 후속 BE3 안정화 전까지 아래 정책을 유지한다.

- `query_signals`는 hard filter가 아니라 soft rerank 신호로만 사용한다.
- 법령 조문 검색은 `legal_ref_ids`가 있을 때 우선 수행한다.
- `law_articles_v1`는 정상 인덱스로 간주하되, 코퍼스 갱신 시 재인덱싱한다.
- 공개 응답에는 내부 `source_url`을 노출하지 않고 `public_url`만 사용한다.
- 법령 grounding이 붙어도 빈 답변은 허용하지 않는다.

## 8. BE3에 넘기는 결론

BE2 검색과 법령 조문 검색 연결은 현재 사용 가능한 상태다.

BE3의 기존 방어 로직도 동작 중이다. 실제로 빈 답변과 답변 생성 오류는 0건이었고,
fallback metadata도 E2E에서 관측됐다.

남은 핵심 리스크는 **법령 grounding 케이스에서 BE3 생성 응답이 JSON 계약을 안정적으로
지키지 못해 기존 fallback 방어까지 도달하는 현상**이다.

BE3 후속 개선에서는 검색/인덱스보다 다음을 우선 확인하면 된다.

- 법령 조문 컨텍스트 포함 프롬프트의 JSON 출력 안정성
- 재시도 프롬프트와 JSON schema 강제 전략
- fallback 진입 전 복구 로직
- fallback 상태에서 `legal_citations`, `legal_citation_warnings`,
  `generation_metadata`를 어떻게 유지할지
