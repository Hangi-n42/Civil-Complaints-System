# BE2 검색 readiness 운영 스모크 체크 runbook

작성일: 2026-06-09

담당: BE2 검색

관련 이슈: #352

## 목적

운영 전 또는 인수인계 직후 BE2 검색/인덱스 readiness를 한 명령으로 재현한다.

이 runbook은 기존 확인 항목을 묶는 용도다. 검색 로직, 생성 로직, ChromaDB metadata
구조는 변경하지 않는다.

## 실행 명령

```bash
python scripts/check_be2_operational_readiness.py
```

기본 실행은 다음을 확인한다.

| 항목 | 확인 내용 |
| --- | --- |
| ChromaDB 검색 신호 metadata | `civil_cases_v1`의 `entity_texts`, `legal_ref_names`, `legal_ref_ids`, `issue_types`, `key_terms`, `responsible_units`, `urgency_level` 적재율 |
| 법령 조문 인덱스 | `law_articles_v1` 접근, 대표 질의 검색, 검색 조문 valid/미검색 조문 invalid 검증 |
| citation 공개 URL 정책 | valid citation에는 `public_url`이 있고 `source_url`은 제거되는지 확인 |
| 개인정보 위험 산출물 | 민원 원문, 검색 snippet, 생성 답변 미리보기 비커밋 원칙 확인 |

스모크 체크 요약은 기본적으로 아래 경로에 저장된다.

```text
reports/retrieval/v3/be2_operational_smoke_check.md
```

ChromaDB 적재율 상세 JSON/Markdown은 기본적으로 `/tmp/be2_operational_smoke_check`에
저장한다. 이 상세 산출물은 `entity_texts`, `key_terms` 원문 값을 해시 prefix로만
남긴다.

## 운영 판단

전체 결과가 `통과`이면 BE2 검색 readiness는 운영 전 필수 스모크 기준을 통과한 것으로
본다.

조건부로 해석해야 하는 항목:

- `entity_texts` 적재율이 낮으면 객체명 기반 rerank 효과는 제한적으로 본다.
- `legal_ref_names`와 `legal_ref_ids`는 적재율뿐 아니라 두 필드의 건수 일치를 함께 본다.
- `responsible_units`는 fallback 값일 수 있으므로 확정 담당부서처럼 표시하지 않는다.
- 법령 grounding 이후 `generation_mode=fast_fallback`이 늘면 BE2 검색 실패가 아니라
  BE3 생성 JSON 안정성 이슈인지 먼저 분리한다.

## 공개 URL/source URL 정책

- ChromaDB metadata의 `source_url`은 내부 원천 확인용이다.
- FE/API 공개 응답에는 `source_url`을 노출하지 않는다.
- 사용자에게 노출되는 법령 citation에는 검증 경로에서 만든 `public_url`만 남긴다.

## 개인정보 및 커밋 원칙

커밋 금지:

- 민원 원문
- 검색 snippet
- 생성 답변 미리보기
- raw E2E JSON/Markdown

필요한 raw 확인은 `/tmp`에만 저장하고 PR에는 요약 수치와 판단만 남긴다.

커밋 가능:

- 해시 처리된 metadata 적재율 요약
- 법령 조문 인덱스 건수/통과 여부
- citation 필드 정책 통과 여부
- 운영 판단과 남은 리스크

## 관련 기존 문서

- `reports/retrieval/v3/be2_readiness_audit.md`
- `reports/retrieval/v3/law_articles_index_check.md`
- `reports/retrieval/v3/law_grounding_qa_e2e_recheck.md`
