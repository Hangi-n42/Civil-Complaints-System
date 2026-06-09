# 법령 조문 인덱스 확인 리포트

작성일: 2026-06-09  
담당: BE2 검색  
관련 이슈: #346

## 1. 목적

로컬 ChromaDB에 새로 인덱싱된 법령 조문 collection `law_articles_v1`가
정상 저장되었는지 확인한다.

이 점검은 읽기 전용으로 수행했다. 법령 조문 인덱스를 다시 빌드하지 않았고,
ChromaDB metadata, 검색 로직, 생성 로직은 변경하지 않았다.

## 2. 확인 명령

```bash
python scripts/check_law_index.py
python scripts/inspect_chromadb.py list
python scripts/inspect_chromadb.py count --collection law_articles_v1
```

추가로 ChromaDB metadata를 읽기 전용으로 순회해 필수 metadata 적재 건수를 확인했다.

## 3. 저장 상태

| 항목 | 결과 |
| --- | ---: |
| ChromaDB collection 존재 여부 | 존재 |
| collection 이름 | `law_articles_v1` |
| 색인 조문 수 | 17,759 |
| 점검 결과 | 통과 |

현재 ChromaDB collection 목록:

| collection |
| --- |
| `civil_cases_v1` |
| `law_articles_v1` |

## 4. 필수 metadata 적재 상태

| metadata | 적재 건수 | 적재율 |
| --- | ---: | ---: |
| `law_id` | 17,759 | 100.00% |
| `law_name` | 17,759 | 100.00% |
| `article_no` | 17,759 | 100.00% |
| `doc_type` | 17,759 | 100.00% |
| `enforce_date` | 17,759 | 100.00% |
| `source_url` | 17,759 | 100.00% |

## 5. 검색 확인

`scripts/check_law_index.py` 기준 4개 대표 질의에서 법령 필터 검색과 인용검증이
동작했다.

| 질의 유형 | 법령 필터 | 검색 결과 예 | 인용검증 |
| --- | --- | --- | --- |
| 무허가 가설건축물 이행강제금 | `건축법(001823)` | `건축법 제80조`, `제80조의2` | valid 1, invalid 1 차단 |
| 3톤 미만 지게차 적성검사 | `건설기계관리법(000239)` | `건설기계관리법 제29조` | valid 1, invalid 1 차단 |
| 실업급여 수급 자격 | `고용보험법(001761)` | `고용보험법 제37조`, `제37조의2` | valid 1, invalid 1 차단 |
| 불법 주정차 과태료 | `도로교통법(001638)` | `도로교통법 제160조` | valid 1, invalid 1 차단 |

## 6. 운영 판단

법령 조문 인덱스는 현재 로컬 ChromaDB 기준으로 **정상 저장**으로 판단한다.

근거:

- `law_articles_v1` collection이 존재한다.
- 조문 17,759건이 색인되어 있다.
- 필수 metadata가 전 건에 적재되어 있다.
- 법령별 `law_id` 필터 검색이 동작한다.
- 인용검증에서 검색된 조문은 valid 처리되고, 검색되지 않은 조문은 invalid로 차단된다.

## 7. 주의사항

- ChromaDB metadata의 `source_url`은 내부 수집/원천 확인용 값이다.
- FE/API 공개 응답에는 `source_url`을 노출하지 않는다.
- 사용자 응답에는 검증 경로에서 생성되는 `public_url`만 노출한다.
- 법령 조문은 현행 스냅샷 기준이므로 법령 코퍼스 갱신 시 `law_articles_v1` 재인덱싱이 필요하다.

## 8. 결론

BE2/BE3 법령 grounding에 필요한 `law_articles_v1` 조문 인덱스는 현재 정상이다.

기존 readiness 문서의 "법령 인덱스 상태 확인 필요" 항목은 현재 로컬 기준
"확인 완료"로 업데이트할 수 있다.
