# responsible_units source 구분 점검

작성일: 2026-06-09  
담당: BE2 검색  
관련 이슈: #342

## 1. 목적

BE2 readiness 점검에서 `responsible_units` 적재율은 100%로 확인됐다.
하지만 이 값이 실제 BE1 `responsible_unit` 후보인지, 기존 `category/source`
fallback으로 채워진 값인지 구분이 필요했다.

이 문서는 현재 ChromaDB metadata 기준으로 `responsible_units`의 출처를 진단하고,
운영에서 담당부서 신호를 어떻게 해석해야 하는지 정리한다.

민원 원문, 검색 snippet, 생성 답변 미리보기 등 개인정보 위험이 있는 raw 내용은
포함하지 않았다.

## 2. 점검 대상

| 항목 | 값 |
| --- | ---: |
| collection | `civil_cases_v1` |
| persist dir | `data/chroma_db` |
| 전체 건수 | 9,132 |
| 점검 건수 | 9,132 |
| `responsible_units` 적재 건수 | 9,132 |
| `responsible_units` 적재율 | 100.00% |

## 3. 점검 방법

각 metadata row에서 다음 값을 비교했다.

- `responsible_units`
- `category`
- `source`

먼저 raw `category/source` 값과 비교했고, 이후 기존 backfill 규칙과 동일하게
빈 값, `-`, `unknown`, `미분류`를 제외한 cleaned `category/source`와 다시 비교했다.

또한 `responsible_units_source`, `responsible_unit_source`,
`responsible_units_origin`, `responsible_unit_origin` 같은 명시적 출처 metadata가
있는지도 확인했다.

## 4. 핵심 결과

명시적 source metadata:

| metadata key | 적재 건수 |
| --- | ---: |
| `responsible_units_source` | 0 |
| `responsible_unit_source` | 0 |
| `responsible_units_origin` | 0 |
| `responsible_unit_origin` | 0 |

raw `category/source` 비교:

| 분류 | 건수 | 비율 |
| --- | ---: | ---: |
| `responsible_units`가 raw `category/source`와 정확히 일치 | 7,734 | 84.69% |
| `responsible_units`가 raw `category/source`의 부분집합 | 1,398 | 15.31% |
| 일부만 겹침 | 0 | 0.00% |
| 전혀 겹치지 않음 | 0 | 0.00% |
| `responsible_units` 빈 값 | 0 | 0.00% |

cleaned `category/source` 비교:

| 분류 | 건수 | 비율 |
| --- | ---: | ---: |
| cleaned `category/source` fallback으로 정확히 설명 가능 | 9,132 | 100.00% |

## 5. 상위 값 분포

상위 `responsible_units`:

| 값 | 건수 |
| --- | ---: |
| `국토교통부` | 2,131 |
| `서울시` | 1,435 |
| `고용노동부` | 1,309 |
| `중소벤처기업부` | 1,044 |
| `문화관광` | 946 |
| `국립아시아문화전당` | 946 |
| `성남시` | 844 |
| `안양시` | 469 |
| `제주특별자치도` | 429 |
| `건설안전과` | 248 |

상위 `category/source` 조합:

| 값 | 건수 |
| --- | ---: |
| `unknown|고용노동부` | 1,042 |
| `문화관광|국립아시아문화전당` | 946 |
| `unknown|서울시` | 295 |
| `건설안전과|국토교통부` | 242 |
| `경영 전략|중소벤처기업부` | 211 |
| `건축안전과|국토교통부` | 193 |
| `주택건설공급과|국토교통부` | 185 |
| `건축정책과|국토교통부` | 177 |
| `인사/노무|중소벤처기업부` | 174 |
| `수출입|중소벤처기업부` | 170 |

## 6. 판단

현재 ChromaDB의 `responsible_units`는 실제 BE1 `responsible_unit` 후보로 구분할
수 없다. 전체 9,132건이 cleaned `category/source` fallback 패턴으로 설명된다.

따라서 `responsible_units` 적재율 100%는 "담당부서 후보가 완전하다"는 뜻이 아니라,
"기존 category/source 기반 fallback 값이 모든 row에 들어 있다"는 뜻으로 해석해야 한다.

BE2 운영 판단:

- `responsible_units`는 계속 약한 soft rerank 신호로만 사용한다.
- 현재 값은 확정 담당부서처럼 사용자에게 노출하거나 강한 가중치로 쓰면 안 된다.
- 기존 가중치 `+0.03`은 보수적인 수준이므로 유지 가능하다.
- 담당부서 기반 품질 개선을 하려면 출처 metadata를 먼저 추가해야 한다.

## 7. 권장 후속 작업

신규 인덱싱부터 다음 중 하나의 출처 필드를 추가하는 것을 권장한다.

```jsonc
{
  "responsible_units": "건축과",
  "responsible_units_source": "be1_structured"
}
```

fallback일 경우:

```jsonc
{
  "responsible_units": "건축안전과|국토교통부",
  "responsible_units_source": "category_source_fallback"
}
```

권장 source 값:

| source | 의미 |
| --- | --- |
| `be1_structured` | BE1 `responsible_unit` 후보에서 온 값 |
| `category_source_fallback` | 기존 category/source 기반 fallback |
| `missing` | 담당부서 후보 없음 |

## 8. 결론

BE2 검색은 현재 `responsible_units`를 사용할 수 있지만, 이 값은 실제 BE1 담당부서
후보가 아니라 fallback으로 보는 것이 안전하다.

운영에서는 담당부서 신호를 약한 보조 신호로만 유지하고, 후속 PR에서
`responsible_units_source` 같은 출처 metadata를 추가해 실제 BE1 담당부서 후보와
fallback을 구분하는 것이 좋다.
