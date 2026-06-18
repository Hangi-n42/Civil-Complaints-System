# 부서 라우팅 기반 민원 카테고리 매핑

## 목적

프론트엔드에서 민원 처리인이 한눈에 볼 수 있는 표시용 카테고리를 제공한다. 기존 원천 `category` 값은 기관/데이터셋마다 흔들리고 검색 필터 계약에도 쓰이므로 덮어쓰지 않는다. 대신 BE1 구조화 결과에 `civil_category`를 추가하고, 프론트는 이 값을 우선 표시한다.

## 기준 카테고리

부산광역시 공식 `분야별정보` 메뉴의 대분류를 기준으로 한다.

- 경제
- 일자리·노동·교육
- 사회복지
- 여성·가족
- 보건·건강
- 도시·건축·주택
- 안전
- 공원녹지·환경
- 교통·물류
- 해양농수산
- 행정
- 문화체육관광

참고 출처: https://www.busan.go.kr/index, https://www.busan.go.kr/depart/index

## 출력 형식

```json
{
  "civil_category": {
    "primary": "교통·물류",
    "secondary": "버스",
    "secondary_candidates": ["버스", "대중교통"],
    "confidence": 0.84,
    "evidence": ["대중교통과", "버스"],
    "source": "responsible_unit+keyword"
  }
}
```

## 설계 원칙

- `category` 원본 필드는 유지한다.
- 부서 라우팅 결과(`responsible_unit`)를 가장 강한 근거로 사용한다.
- 같은 부서가 여러 주제를 다룰 수 있으므로 `primary`와 `secondary_candidates`를 함께 제공한다.
- 부서 신호가 없거나 fallback이면 원문, entity_texts, key_terms, 기존 category를 보조 신호로 사용한다.
- 근거가 부족하면 `행정 > 일반민원`으로 보수적으로 분류한다.

## 색인/검색 메타데이터

BE2 인덱싱 payload와 Chroma metadata에는 검색/검증 편의를 위해 아래 필드를 납작하게 보존한다.

- `civil_category_primary`
- `civil_category_secondary`
- `civil_category_source`

기존 `category` 필터는 유지되며, 새 필드는 표시와 분석용 보조 metadata다.

## 프론트 표시 정책

프론트는 `category_display` 또는 `civil_category`가 있으면 `대분류 > 세부태그` 형태로 보여준다. 없으면 기존 `category`를 그대로 표시한다.

검색 필터의 기존 `category` 값은 BE2 인덱스의 원천 category와 호환되어야 하므로 이번 변경에서 새 대분류로 대체하지 않는다.

## 한계

- 자동 매핑은 행정조직과 민원 본문을 기준으로 한 deterministic rule이다.
- 담당부서 후보가 비어 있거나 본문이 짧으면 보수적으로 분류될 수 있다.
- 세부태그는 부산시 사이트 메뉴와 부서 업무명을 참고한 운영용 태그이며, 부산시의 별도 공식 민원 분류 코드가 아니다.
