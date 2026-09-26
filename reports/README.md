# 실행 산출물과 평가 절차

- 문서 버전: v2.0
- 기준일: 2026-09-26

과거 Markdown 결과 보고서는 [모듈별 experiments](../experiments/README.md)로 이동했다. JSON·JSONL·TSV·캐시·그림은 기존 스크립트가 읽거나 생성하므로 경로를 유지했다. 스크립트 실행 시 Markdown 보고서가 다시 이 폴더에 생성될 수 있다. 검토가 끝난 결과를 보관할 때 실험 모듈별 디렉터리에 이동하고 원래 경로·실행 조건을 남긴다.

다음 문서는 실행·평가 절차이므로 유지한다.

- [Request segment limited 정책](request_segment_assist_limited_v2_runtime_policy.md)
- [Request segment strict 활성화](request_segment_assist_v2_strict_activation_guide.md)
- [검색 smoke check](retrieval/v3/be2_operational_smoke_check_runbook.md)
- [판정 프롬프트](retrieval/v3/codex_judge_prompt.md)
- [평가 프로토콜](retrieval/v3/eval_protocol.md)
- [검색 관련성 rubric](retrieval/version_neutral/relevance_rubric_v3.md)

각 절차의 작성 당시 적용 범위를 확인한다. 신규 회사 지식 제품의 완료 기준은 [메인 PRD](../docs/00_overview/company_knowledge_prd.md)를 따른다.
