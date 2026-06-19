# 평가셋 재구축 선결 검증

> 새 코퍼스(`civil_cases_v3`, 25,565건)로 qrels를 재구축하기 전, 선결 점검에서 제기된
> 자기참조·BM25 문제를 실제로 검증한다. (`scripts/verify_rebuild_prereqs.py`)

## 1. 자기참조 — `exclude_case_id`로 해결 (검증 완료)

- 평가 쿼리 **100/100**의 원본 민원이 `civil_cases_v3`에 `CASE-{source_id}`로 포함됨 →
  검색하면 자기 자신이 (대부분 top1로) 떠 자기참조 편향.
- `service.search(exclude_case_id="CASE-{source_id}")`로 **6/6 제외 성공** (exclude無 self 포함
  6/6, 그중 top1 4/6 → exclude有 self 포함 0/6).
- → **새 채점/평가 스크립트는 각 쿼리에 `exclude_case_id` 주입 필수.**

## 2. BM25 재색인 — 불필요 (앞선 진단 정정)

- `service.search`는 `HybridRetriever`가 컬렉션에서 BM25를 **메모리 lazy 빌드**한다
  ([hybrid.py:89-109](../../../app/retrieval/search/hybrid.py)). `data/bm25_index/`(v1 레거시)는
  `app/retrieval/pipeline/`(별도 평가 프레임워크)만 사용 → **service 경로와 무관**.
- hybrid v3(25,565) 검색 **6/6 정상 동작** 확인(첫 호출 시 BM25 자동 빌드).
- → **BM25 재색인 작업 불필요.** ("BM25 재색인 필요"라던 선결 진단을 정정.)

## 3. 추가 관찰

- 코퍼스에 `CASE-POLICY-*`(`raw_civil_policy_qna` 정책 Q&A) 문서가 섞여 있음(Q-0006 top1
  = `CASE-POLICY-6891594`). 검색 대상에 정책 Q&A가 포함된 것이 의도된 구성인지 확인 필요.

## 결론

| 선결 | 상태 |
|---|---|
| 자기참조 제외 | ✅ `exclude_case_id`로 해결 (검증) |
| BM25 재색인 | ✅ 불필요 (HybridRetriever lazy 빌드) |
| hybrid v3 동작 | ✅ 정상 (25,565 빌드) |

**다음(전량 채점 — 현재 스톱):** 후보 풀 추출·채점 단계에서 `exclude_case_id` 적용 + v3.1 루브릭 사용. 코퍼스 내 정책 Q&A 포함 여부 결정.
