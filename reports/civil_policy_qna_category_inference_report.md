# 정책 Q&A consulting_category 추론 고도화 리포트

## 배경

`scripts/data/raw_civil_policy_qna/details` 원천은 `subjList`가 대부분 비어 있어 기존 전처리 결과가 전부 `consulting_category=미분류`로 생성됐다. 이 상태에서는 BE1 구조화가 실패하지는 않지만, FE 카테고리 필터와 검색 metadata, 긴급도/표시용 카테고리 보조 신호가 약해진다.

## 계획

1. 원천 `subjList`가 있으면 그대로 보존한다.
2. `subjList`가 비어 있을 때만 기관명, 담당부서명, 법령명, 제목, 민원인 질문을 근거로 추론한다.
3. 추론 카테고리는 부산시 분야별정보 대분류와 세부태그를 함께 담는 `대분류 > 세부태그` 형식으로 만든다.
4. 상담사 답변은 길고 법령 설명이 많아 속도와 오분류 리스크가 있으므로 카테고리 추론 근거에서는 제외한다.
5. 단서가 약하면 억지로 채우지 않고 `미분류`를 유지한다.

## 계획 평가

가장 큰 리스크는 기관명 하나만 보고 광범위하게 오분류하는 것이다. 이를 줄이기 위해 제목/질문과 법령명을 기관명보다 강한 신호로 두고, `민원` 같은 일반어는 추론 규칙에서 제외했다. 운영 추론 모델이나 검색 결과를 gold처럼 사용하지 않아 평가 누수도 만들지 않는다.

## 구현 요약

- `scripts/preprocess_civil_policy_qna.py`
  - `PolicyCategoryRule`과 `POLICY_CATEGORY_RULES` 추가
  - `infer_policy_category()` 추가
  - `resolve_policy_category()` 추가
  - `convert_detail_payload()`에서 `subjList` 우선, 없을 때 추론 카테고리 사용
- `app/tests/unit/test_preprocess_civil_policy_qna.py`
  - 원천 `subjList` 우선 보존 테스트
  - 기관/법령/본문 기반 추론 테스트
  - 약한 신호는 `미분류` 유지 테스트

## 검증 결과

최신 규칙으로 `data/processed/civil_policy_qna_processed.json`을 재생성했다.

| 항목 | 결과 |
| --- | ---: |
| 전체 레코드 | 16,433 |
| 파싱 성공 | 16,433 |
| 추론/원천 카테고리 채움 | 14,535 |
| 미분류 유지 | 1,898 |
| 고유 카테고리 | 43 |
| 구조화용 빈 text | 0 |
| 검색용 빈 text | 0 |

상위 카테고리:

| 카테고리 | 건수 |
| --- | ---: |
| 일자리·노동·교육 > 교육 | 2,810 |
| 미분류 | 1,898 |
| 경제 > 세무 | 1,163 |
| 교통·물류 > 도로시설물 | 955 |
| 보건·건강 > 식품 | 947 |
| 안전 > 생활안전 | 808 |

실행한 테스트:

```powershell
.\civil\Scripts\python.exe -m pytest app\tests\unit\test_preprocess_civil_policy_qna.py app\tests\unit\test_preprocessing_adapter.py app\tests\unit\test_civil_category.py app\tests\unit\test_build_index_contract.py -q
```

결과: `30 passed`

## 남은 리스크

- 자동 규칙 기반 추론이므로 사람 검수 카테고리와 완전히 같다고 볼 수 없다.
- `미분류` 1,898건은 일부러 남긴 보수적 잔여분이다. 무리하게 채우면 FE 필터와 검색 metadata 오염 가능성이 커진다.
- 검색 인덱스에 반영하려면 새로 생성한 processed 파일 기준으로 재색인이 필요하다.
