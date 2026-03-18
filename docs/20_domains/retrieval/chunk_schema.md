# 청크 메타데이터 구조 초안 (Week 1, BE2)

문서 버전: v1.0  
작성일: 2026-03-17  
담당: BE2 (민건)

## 1. 목적

구조화 결과를 벡터 인덱싱 단위로 변환할 때 필요한 청크 구조를 고정한다.

## 2. MVP 청크 전략

- 기본 전략: 1건 민원 = 1개 `combined` 청크
- 이유: Week 2 PoC에서 파이프라인 안정성과 속도를 우선
- 후속 확장: `observation`, `request` 분리 청크는 품질 튜닝 단계에서 추가

## 3. SearchChunk v1

```json
{
  "chunk_id": "CASE-2026-000123__chunk-0",
  "case_id": "CASE-2026-000123",
  "chunk_text": "[observation]\n...\n[result]\n...\n[request]\n...\n[context]\n...",
  "chunk_type": "combined",
  "source": "civil_portal",
  "created_at": "2026-03-05T10:15:00+09:00",
  "category": "도로안전",
  "region": "서울시 강남구",
  "entity_labels": ["LOCATION", "FACILITY", "HAZARD"],
  "entity_texts": ["OO동 사거리", "가로등", "전도 위험"],
  "metadata": {
    "structuring_confidence": 0.88,
    "content_type": "full"
  }
}
```

## 4. 필드 규칙

| 필드 | 규칙 |
| --- | --- |
| `chunk_id` | `<case_id>__chunk-<index>` 형식 고정 |
| `chunk_type` | MVP에서는 `combined`만 사용 |
| `chunk_text` | 4요소를 순서대로 결합, 빈 항목은 생략 |
| `entity_labels` | 라벨 중복 제거 후 저장 |
| `metadata.structuring_confidence` | 4요소 confidence 평균(가능 시) |

## 5. 인덱싱 전 변환 로직

1. 구조화 결과 수신
2. 필수 메타데이터 보정 (`case_id`, `created_at`, `source`)
3. `chunk_text` 구성
4. `chunk_id` 생성
5. 벡터DB 저장

## 6. citation 정합성 규칙

QA 응답에서 citation은 아래 키를 반드시 포함한다.

- `chunk_id`
- `case_id`
- `snippet`

추가 권장 키:
- `relevance_score`

## 7. 리스크 및 대응

### 리스크: combined 청크가 길어 검색 정확도 저하
- 징후: 관련 없는 문맥까지 같이 매칭됨
- 원인: 단일 청크에 정보 과다
- 예방책: chunk_text 최대 길이 제한(예: 1200자)
- 대응책: `request` 중심 보조 청크 추가
- 최악의 경우 폴백안: 4요소별 멀티 청크 인덱싱으로 전환
