# 문서 감사·정리 기록

- 문서 버전: v2.0
- 기준일: 2026-09-26

## 기준과 완료 범위

신규 회사 지식 제품을 주 기준으로 재편했다. PRD 원문의 요구사항·재사용 결정은 PRD/설계/구현/마일스톤으로 역할을 나눴다. 기존 민원 PRD·아키텍처는 이름과 지위를 명확히 했으며 최초 정리에서는 이전 4개 진입 경로를 이동 안내로 유지했으며, 아래 후속 정리에서 제거·교체했다.

실행 문서·주요 개요는 현재 코드와 정적으로 대조했다. 전체 역사 문서의 모든 주장을 재검증하거나 과거 실험을 재실행하지 않았다. 기존 애플리케이션 변경·파일럿 고정 입력·실험 JSON은 이번 정리 대상이 아니다.

과거 실험 보고서 99개와 기타 문서 14개, 총 113개를 재배치했다. 원작성일과 결과를 보존하고 보관 정리일만 덧붙였다. 지난 감사표는 아래 이동 목록의 archive에서 확인한다.

## 계속 유지하는 문서 체계

| 위치 | 지위·처리 |
|---|---|
| `05_plans/company_knowledge/` | 신규 제품 상세 설계·구현·마일스톤 |
| `00_overview/` | 메인 PRD v1.4·ADR v3.0·공통 개요·기존 민원 구현 |
| `10_contracts/` | 기존 계약; 주차별 자료 전체를 현재 계약으로 승격하지 않음 |
| `20_domains/` | 기존 도메인 기준 |
| `30_manuals/` | 실행·평가 절차; 갱신 범위는 각 문서 날짜 참고 |
| `40_logs/`, `50_issues/`, `60_specs/` | 남아 있는 이력·이슈·설계. 전체 재검증 미수행 |
| `70_research/company_knowledge/` | 신규 제품 선정 근거·파일럿 기록 |
| `90_archive/` | 종료된 계획·이전 감사 |
| `../experiments/` | 모듈별 과거 결과 |

## 최초 이동 명세(후속 배치는 마지막 절 참조)

| 이전 경로 | 현재 경로 |
|---|---|
| `docs/00_overview/architecture.md` | [docs/00_overview/complaint_system_architecture.md](00_overview/complaint_system_architecture.md) |
| `docs/00_overview/company_knowledge_milestones.md` | [docs/05_plans/company_knowledge/milestones.md](05_plans/company_knowledge/milestones.md) |
| `docs/00_overview/company_knowledge_prd.md` | [docs/05_plans/company_knowledge/prd.md](00_overview/company_knowledge_prd.md) |
| `docs/00_overview/mvp_scope.md` | [docs/90_archive/complaint_system/mvp_scope.md](90_archive/complaint_system/mvp_scope.md) |
| `docs/00_overview/prd.md` | [docs/00_overview/complaint_system_prd.md](00_overview/complaint_system_prd.md) |
| `docs/00_overview/wbs_8weeks_v2_updated.md` | [docs/90_archive/complaint_system/wbs_8weeks_v2_updated.md](90_archive/complaint_system/wbs_8weeks_v2_updated.md) |
| `docs/20_domains/retrieval/eval_overhaul_summary.md` | [experiments/retrieval/docs/20_domains/retrieval/eval_overhaul_summary.md](../experiments/retrieval/docs/20_domains/retrieval/eval_overhaul_summary.md) |
| `docs/40_delivery/BE2_adaptive_rag_comparison.md` | [experiments/retrieval/docs/40_delivery/BE2_adaptive_rag_comparison.md](../experiments/retrieval/docs/40_delivery/BE2_adaptive_rag_comparison.md) |
| `docs/40_delivery/BE2_final_completion_report.md` | [experiments/retrieval/docs/40_delivery/BE2_final_completion_report.md](../experiments/retrieval/docs/40_delivery/BE2_final_completion_report.md) |
| `docs/40_delivery/BE2_final_kpi_snapshot.md` | [experiments/retrieval/docs/40_delivery/BE2_final_kpi_snapshot.md](../experiments/retrieval/docs/40_delivery/BE2_final_kpi_snapshot.md) |
| `docs/40_delivery/issue387_llm_rubric_completion_review.md` | [experiments/evaluation/docs/40_delivery/issue387_llm_rubric_completion_review.md](../experiments/evaluation/docs/40_delivery/issue387_llm_rubric_completion_review.md) |
| `docs/40_delivery/rubric_summary.md` | [experiments/evaluation/docs/40_delivery/rubric_summary.md](../experiments/evaluation/docs/40_delivery/rubric_summary.md) |
| `docs/40_delivery/week11/benchmark_report/answer_score_transition_report_Fir.md` | [experiments/evaluation/docs/40_delivery/week11/benchmark_report/answer_score_transition_report_Fir.md](../experiments/evaluation/docs/40_delivery/week11/benchmark_report/answer_score_transition_report_Fir.md) |
| `docs/40_delivery/week11/benchmark_report/answer_score_transition_report_Sec.md` | [experiments/evaluation/docs/40_delivery/week11/benchmark_report/answer_score_transition_report_Sec.md](../experiments/evaluation/docs/40_delivery/week11/benchmark_report/answer_score_transition_report_Sec.md) |
| `docs/40_delivery/week11/benchmark_report/rand100_final_benchmark_comparison_report.md` | [experiments/generation/docs/40_delivery/week11/benchmark_report/rand100_final_benchmark_comparison_report.md](../experiments/generation/docs/40_delivery/week11/benchmark_report/rand100_final_benchmark_comparison_report.md) |
| `docs/40_delivery/week4/WEEK4_BE3_AX4_SAMPLE10_LEGACY_VS_NEW_SCRIPT_REPORT.md` | [experiments/generation/docs/40_delivery/week4/WEEK4_BE3_AX4_SAMPLE10_LEGACY_VS_NEW_SCRIPT_REPORT.md](../experiments/generation/docs/40_delivery/week4/WEEK4_BE3_AX4_SAMPLE10_LEGACY_VS_NEW_SCRIPT_REPORT.md) |
| `docs/40_delivery/week5/WEEK5_BE3_4_MODEL_SAMPLE50_COMPARISON_REPORT.md` | [experiments/generation/docs/40_delivery/week5/WEEK5_BE3_4_MODEL_SAMPLE50_COMPARISON_REPORT.md](../experiments/generation/docs/40_delivery/week5/WEEK5_BE3_4_MODEL_SAMPLE50_COMPARISON_REPORT.md) |
| `docs/40_delivery/week5/WEEK5_BE3_WEEK4_VS_WEEK5_SAMPLE50_COMPARISON_REPORT.md` | [experiments/generation/docs/40_delivery/week5/WEEK5_BE3_WEEK4_VS_WEEK5_SAMPLE50_COMPARISON_REPORT.md](../experiments/generation/docs/40_delivery/week5/WEEK5_BE3_WEEK4_VS_WEEK5_SAMPLE50_COMPARISON_REPORT.md) |
| `docs/40_delivery/week6/WEEK6_BE3_PPT_ONE_PAGE_SUMMARY.md` | [experiments/generation/docs/40_delivery/week6/WEEK6_BE3_PPT_ONE_PAGE_SUMMARY.md](../experiments/generation/docs/40_delivery/week6/WEEK6_BE3_PPT_ONE_PAGE_SUMMARY.md) |
| `docs/40_delivery/week6/api_4model_comparison_same_condition.md` | [experiments/generation/docs/40_delivery/week6/api_4model_comparison_same_condition.md](../experiments/generation/docs/40_delivery/week6/api_4model_comparison_same_condition.md) |
| `docs/40_delivery/week9/test_structured.md` | [experiments/structuring/docs/40_delivery/week9/test_structured.md](../experiments/structuring/docs/40_delivery/week9/test_structured.md) |
| `docs/40_delivery/week9/test_structured2.md` | [experiments/structuring/docs/40_delivery/week9/test_structured2.md](../experiments/structuring/docs/40_delivery/week9/test_structured2.md) |
| `docs/50_issues/adaptive_router_decision.md` | [experiments/retrieval/docs/50_issues/adaptive_router_decision.md](../experiments/retrieval/docs/50_issues/adaptive_router_decision.md) |
| `docs/50_issues/company_knowledge_pilot_freeze_2026-09-26.md` | [docs/70_research/company_knowledge/company_knowledge_pilot_freeze_2026-09-26.md](70_research/company_knowledge/company_knowledge_pilot_freeze_2026-09-26.md) |
| `docs/50_issues/company_knowledge_pilot_review_2026-09-26.md` | [docs/70_research/company_knowledge/company_knowledge_pilot_review_2026-09-26.md](70_research/company_knowledge/company_knowledge_pilot_review_2026-09-26.md) |
| `docs/50_issues/company_knowledge_prd_review_2026-09-25.md` | [docs/70_research/company_knowledge/company_knowledge_prd_review_2026-09-25.md](70_research/company_knowledge/company_knowledge_prd_review_2026-09-25.md) |
| `docs/50_issues/company_knowledge_reuse_documents_research_2026-09-26.md` | [docs/70_research/company_knowledge/company_knowledge_reuse_documents_research_2026-09-26.md](70_research/company_knowledge/company_knowledge_reuse_documents_research_2026-09-26.md) |
| `docs/50_issues/company_knowledge_reuse_extraction_research_2026-09-26.md` | [docs/70_research/company_knowledge/company_knowledge_reuse_extraction_research_2026-09-26.md](70_research/company_knowledge/company_knowledge_reuse_extraction_research_2026-09-26.md) |
| `docs/50_issues/company_knowledge_reuse_graph_research_2026-09-26.md` | [docs/70_research/company_knowledge/company_knowledge_reuse_graph_research_2026-09-26.md](70_research/company_knowledge/company_knowledge_reuse_graph_research_2026-09-26.md) |
| `docs/50_issues/company_knowledge_reuse_research_2026-09-26.md` | [docs/70_research/company_knowledge/company_knowledge_reuse_research_2026-09-26.md](70_research/company_knowledge/company_knowledge_reuse_research_2026-09-26.md) |
| `docs/50_issues/pr466_intelligence_fe_check_verification.md` | [experiments/complaint_intelligence/docs/50_issues/pr466_intelligence_fe_check_verification.md](../experiments/complaint_intelligence/docs/50_issues/pr466_intelligence_fe_check_verification.md) |
| `docs/50_issues/reranker_diagnosis.md` | [experiments/retrieval/docs/50_issues/reranker_diagnosis.md](../experiments/retrieval/docs/50_issues/reranker_diagnosis.md) |
| `docs/50_issues/risk2_pool_bias_decision.md` | [experiments/retrieval/docs/50_issues/risk2_pool_bias_decision.md](../experiments/retrieval/docs/50_issues/risk2_pool_bias_decision.md) |
| `docs/DOCS_AUDIT.md` | [docs/90_archive/documentation/docs_audit_2026-06-21.md](90_archive/documentation/docs_audit_2026-06-21.md) |
| `reports/WEEK2_FIXES_SUMMARY.md` | [experiments/structuring/reports/WEEK2_FIXES_SUMMARY.md](../experiments/structuring/reports/WEEK2_FIXES_SUMMARY.md) |
| `reports/civil_policy_qna_category_inference_report.md` | [experiments/structuring/reports/civil_policy_qna_category_inference_report.md](../experiments/structuring/reports/civil_policy_qna_category_inference_report.md) |
| `reports/complaint_intelligence_eval_comparison_fake.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_eval_comparison_fake.md](../experiments/complaint_intelligence/reports/complaint_intelligence_eval_comparison_fake.md) |
| `reports/complaint_intelligence_eval_report.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_eval_report.md](../experiments/complaint_intelligence/reports/complaint_intelligence_eval_report.md) |
| `reports/complaint_intelligence_eval_report_after_fake.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_after_fake.md](../experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_after_fake.md) |
| `reports/complaint_intelligence_eval_report_baseline_fake.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_baseline_fake.md](../experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_baseline_fake.md) |
| `reports/complaint_intelligence_eval_report_final_fake.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_final_fake.md](../experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_final_fake.md) |
| `reports/complaint_intelligence_eval_report_final_local.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_final_local.md](../experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_final_local.md) |
| `reports/complaint_intelligence_eval_report_local.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_local.md](../experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_local.md) |
| `reports/complaint_intelligence_eval_report_local_action_rubric.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_local_action_rubric.md](../experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_local_action_rubric.md) |
| `reports/complaint_intelligence_eval_report_local_compact.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_local_compact.md](../experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_local_compact.md) |
| `reports/complaint_intelligence_eval_report_local_full.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_local_full.md](../experiments/complaint_intelligence/reports/complaint_intelligence_eval_report_local_full.md) |
| `reports/complaint_intelligence_final_improvement_comparison.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_final_improvement_comparison.md](../experiments/complaint_intelligence/reports/complaint_intelligence_final_improvement_comparison.md) |
| `reports/complaint_intelligence_holdout_eval_report.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_holdout_eval_report.md](../experiments/complaint_intelligence/reports/complaint_intelligence_holdout_eval_report.md) |
| `reports/complaint_intelligence_local_llm_action_rubric_samples.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_local_llm_action_rubric_samples.md](../experiments/complaint_intelligence/reports/complaint_intelligence_local_llm_action_rubric_samples.md) |
| `reports/complaint_intelligence_local_llm_insight_samples.md` | [experiments/complaint_intelligence/reports/complaint_intelligence_local_llm_insight_samples.md](../experiments/complaint_intelligence/reports/complaint_intelligence_local_llm_insight_samples.md) |
| `reports/duplicate_merge_batch_performance_report.md` | [experiments/duplicate_merge/reports/duplicate_merge_batch_performance_report.md](../experiments/duplicate_merge/reports/duplicate_merge_batch_performance_report.md) |
| `reports/duplicate_merge_evaluation_report.md` | [experiments/duplicate_merge/reports/duplicate_merge_evaluation_report.md](../experiments/duplicate_merge/reports/duplicate_merge_evaluation_report.md) |
| `reports/duplicate_merge_followup_hardening_report.md` | [experiments/duplicate_merge/reports/duplicate_merge_followup_hardening_report.md](../experiments/duplicate_merge/reports/duplicate_merge_followup_hardening_report.md) |
| `reports/duplicate_merge_labeled_eval_report.md` | [experiments/duplicate_merge/reports/duplicate_merge_labeled_eval_report.md](../experiments/duplicate_merge/reports/duplicate_merge_labeled_eval_report.md) |
| `reports/duplicate_merge_real_holdout_eval_report.md` | [experiments/duplicate_merge/reports/duplicate_merge_real_holdout_eval_report.md](../experiments/duplicate_merge/reports/duplicate_merge_real_holdout_eval_report.md) |
| `reports/request_segment_assist_limited_v2_replay.md` | [experiments/structuring/reports/request_segment_assist_limited_v2_replay.md](../experiments/structuring/reports/request_segment_assist_limited_v2_replay.md) |
| `reports/request_segment_llm_assist_limited_optimization_report.md` | [experiments/structuring/reports/request_segment_llm_assist_limited_optimization_report.md](../experiments/structuring/reports/request_segment_llm_assist_limited_optimization_report.md) |
| `reports/request_segment_llm_condition_b_shadow_100_human_review_summary.md` | [experiments/structuring/reports/request_segment_llm_condition_b_shadow_100_human_review_summary.md](../experiments/structuring/reports/request_segment_llm_condition_b_shadow_100_human_review_summary.md) |
| `reports/request_segment_llm_condition_b_shadow_100_report.md` | [experiments/structuring/reports/request_segment_llm_condition_b_shadow_100_report.md](../experiments/structuring/reports/request_segment_llm_condition_b_shadow_100_report.md) |
| `reports/request_segment_llm_condition_b_shadow_100_review.md` | [experiments/structuring/reports/request_segment_llm_condition_b_shadow_100_review.md](../experiments/structuring/reports/request_segment_llm_condition_b_shadow_100_review.md) |
| `reports/request_segment_llm_hybrid_loop_report.md` | [experiments/structuring/reports/request_segment_llm_hybrid_loop_report.md](../experiments/structuring/reports/request_segment_llm_hybrid_loop_report.md) |
| `reports/request_segment_llm_pregate_postprocess_shadow_eval.md` | [experiments/structuring/reports/request_segment_llm_pregate_postprocess_shadow_eval.md](../experiments/structuring/reports/request_segment_llm_pregate_postprocess_shadow_eval.md) |
| `reports/request_segment_llm_pregate_shadow_eval.md` | [experiments/structuring/reports/request_segment_llm_pregate_shadow_eval.md](../experiments/structuring/reports/request_segment_llm_pregate_shadow_eval.md) |
| `reports/request_segment_llm_pregate_shadow_eval_smoke.md` | [experiments/structuring/reports/request_segment_llm_pregate_shadow_eval_smoke.md](../experiments/structuring/reports/request_segment_llm_pregate_shadow_eval_smoke.md) |
| `reports/request_segment_llm_shadow_ab_eval_exaone.md` | [experiments/structuring/reports/request_segment_llm_shadow_ab_eval_exaone.md](../experiments/structuring/reports/request_segment_llm_shadow_ab_eval_exaone.md) |
| `reports/request_segment_llm_shadow_eval_exaone_20260625.md` | [experiments/structuring/reports/request_segment_llm_shadow_eval_exaone_20260625.md](../experiments/structuring/reports/request_segment_llm_shadow_eval_exaone_20260625.md) |
| `reports/request_segment_strict_allow_500_collection_report.md` | [experiments/structuring/reports/request_segment_strict_allow_500_collection_report.md](../experiments/structuring/reports/request_segment_strict_allow_500_collection_report.md) |
| `reports/request_segment_strict_allow_500_human_review_summary.md` | [experiments/structuring/reports/request_segment_strict_allow_500_human_review_summary.md](../experiments/structuring/reports/request_segment_strict_allow_500_human_review_summary.md) |
| `reports/responsible_unit_content_aware_final_report.md` | [experiments/structuring/reports/responsible_unit_content_aware_final_report.md](../experiments/structuring/reports/responsible_unit_content_aware_final_report.md) |
| `reports/responsible_unit_holdout1000_content_aware_labeling_report.md` | [experiments/structuring/reports/responsible_unit_holdout1000_content_aware_labeling_report.md](../experiments/structuring/reports/responsible_unit_holdout1000_content_aware_labeling_report.md) |
| `reports/responsible_unit_task_expansion_summary.md` | [experiments/structuring/reports/responsible_unit_task_expansion_summary.md](../experiments/structuring/reports/responsible_unit_task_expansion_summary.md) |
| `reports/retrieval/v3/be1_restructured_source_pilot10_coverage.md` | [experiments/retrieval/reports/retrieval/v3/be1_restructured_source_pilot10_coverage.md](../experiments/retrieval/reports/retrieval/v3/be1_restructured_source_pilot10_coverage.md) |
| `reports/retrieval/v3/be1_restructured_source_pilot10_search_smoke.md` | [experiments/retrieval/reports/retrieval/v3/be1_restructured_source_pilot10_search_smoke.md](../experiments/retrieval/reports/retrieval/v3/be1_restructured_source_pilot10_search_smoke.md) |
| `reports/retrieval/v3/be1_restructured_source_pilot10_summary.md` | [experiments/retrieval/reports/retrieval/v3/be1_restructured_source_pilot10_summary.md](../experiments/retrieval/reports/retrieval/v3/be1_restructured_source_pilot10_summary.md) |
| `reports/retrieval/v3/be1_restructured_v1_collection_ab.md` | [experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_collection_ab.md](../experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_collection_ab.md) |
| `reports/retrieval/v3/be1_restructured_v1_coverage.md` | [experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_coverage.md](../experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_coverage.md) |
| `reports/retrieval/v3/be1_restructured_v1_local_coverage.md` | [experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_local_coverage.md](../experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_local_coverage.md) |
| `reports/retrieval/v3/be1_restructured_v1_local_search_smoke.md` | [experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_local_search_smoke.md](../experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_local_search_smoke.md) |
| `reports/retrieval/v3/be1_restructured_v1_search_smoke.md` | [experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_search_smoke.md](../experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_search_smoke.md) |
| `reports/retrieval/v3/be1_restructured_v1_summary.md` | [experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_summary.md](../experiments/retrieval/reports/retrieval/v3/be1_restructured_v1_summary.md) |
| `reports/retrieval/v3/be2_operational_smoke_check.md` | [experiments/retrieval/reports/retrieval/v3/be2_operational_smoke_check.md](../experiments/retrieval/reports/retrieval/v3/be2_operational_smoke_check.md) |
| `reports/retrieval/v3/be2_readiness_audit.md` | [experiments/retrieval/reports/retrieval/v3/be2_readiness_audit.md](../experiments/retrieval/reports/retrieval/v3/be2_readiness_audit.md) |
| `reports/retrieval/v3/be3_handoff_e2e_summary.md` | [experiments/retrieval/reports/retrieval/v3/be3_handoff_e2e_summary.md](../experiments/retrieval/reports/retrieval/v3/be3_handoff_e2e_summary.md) |
| `reports/retrieval/v3/chromadb_search_signal_metadata_coverage.md` | [experiments/retrieval/reports/retrieval/v3/chromadb_search_signal_metadata_coverage.md](../experiments/retrieval/reports/retrieval/v3/chromadb_search_signal_metadata_coverage.md) |
| `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_build.md` | [experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_build.md](../experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_build.md) |
| `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_collection_ab.md` | [experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_collection_ab.md](../experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_collection_ab.md) |
| `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_coverage.md` | [experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_coverage.md](../experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_coverage.md) |
| `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_local_build.md` | [experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_local_build.md](../experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_local_build.md) |
| `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_local_coverage.md` | [experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_local_coverage.md](../experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_local_coverage.md) |
| `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_search_smoke.md` | [experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_search_smoke.md](../experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_search_smoke.md) |
| `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_soft_rerank_eval.md` | [experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_soft_rerank_eval.md](../experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_soft_rerank_eval.md) |
| `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_soft_rerank_pilot10.md` | [experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_soft_rerank_pilot10.md](../experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_soft_rerank_pilot10.md) |
| `reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_summary.md` | [experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_summary.md](../experiments/retrieval/reports/retrieval/v3/civil_cases_v1_be1_metadata_v1_summary.md) |
| `reports/retrieval/v3/dept_definitive_v3.md` | [experiments/retrieval/reports/retrieval/v3/dept_definitive_v3.md](../experiments/retrieval/reports/retrieval/v3/dept_definitive_v3.md) |
| `reports/retrieval/v3/grounding_filter_completion_check.md` | [experiments/retrieval/reports/retrieval/v3/grounding_filter_completion_check.md](../experiments/retrieval/reports/retrieval/v3/grounding_filter_completion_check.md) |
| `reports/retrieval/v3/law_articles_index_check.md` | [experiments/retrieval/reports/retrieval/v3/law_articles_index_check.md](../experiments/retrieval/reports/retrieval/v3/law_articles_index_check.md) |
| `reports/retrieval/v3/law_grounding_qa_e2e_recheck.md` | [experiments/retrieval/reports/retrieval/v3/law_grounding_qa_e2e_recheck.md](../experiments/retrieval/reports/retrieval/v3/law_grounding_qa_e2e_recheck.md) |
| `reports/retrieval/v3/metadata_soft_rerank_summary.md` | [experiments/retrieval/reports/retrieval/v3/metadata_soft_rerank_summary.md](../experiments/retrieval/reports/retrieval/v3/metadata_soft_rerank_summary.md) |
| `reports/retrieval/v3/ndcg_eval_civil.md` | [experiments/retrieval/reports/retrieval/v3/ndcg_eval_civil.md](../experiments/retrieval/reports/retrieval/v3/ndcg_eval_civil.md) |
| `reports/retrieval/v3/query_restructure_v1_v3.md` | [experiments/retrieval/reports/retrieval/v3/query_restructure_v1_v3.md](../experiments/retrieval/reports/retrieval/v3/query_restructure_v1_v3.md) |
| `reports/retrieval/v3/responsible_unit_boost_weight_tuning.md` | [experiments/retrieval/reports/retrieval/v3/responsible_unit_boost_weight_tuning.md](../experiments/retrieval/reports/retrieval/v3/responsible_unit_boost_weight_tuning.md) |
| `reports/retrieval/v3/responsible_unit_condensed_eval.md` | [experiments/retrieval/reports/retrieval/v3/responsible_unit_condensed_eval.md](../experiments/retrieval/reports/retrieval/v3/responsible_unit_condensed_eval.md) |
| `reports/retrieval/v3/responsible_unit_eval_pipeline_audit.md` | [experiments/retrieval/reports/retrieval/v3/responsible_unit_eval_pipeline_audit.md](../experiments/retrieval/reports/retrieval/v3/responsible_unit_eval_pipeline_audit.md) |
| `reports/retrieval/v3/responsible_unit_freshdoc_simulation.md` | [experiments/retrieval/reports/retrieval/v3/responsible_unit_freshdoc_simulation.md](../experiments/retrieval/reports/retrieval/v3/responsible_unit_freshdoc_simulation.md) |
| `reports/retrieval/v3/responsible_unit_llm_judge_eval.md` | [experiments/retrieval/reports/retrieval/v3/responsible_unit_llm_judge_eval.md](../experiments/retrieval/reports/retrieval/v3/responsible_unit_llm_judge_eval.md) |
| `reports/retrieval/v3/responsible_unit_query_signal_ab.md` | [experiments/retrieval/reports/retrieval/v3/responsible_unit_query_signal_ab.md](../experiments/retrieval/reports/retrieval/v3/responsible_unit_query_signal_ab.md) |
| `reports/retrieval/v3/responsible_units_source_audit.md` | [experiments/retrieval/reports/retrieval/v3/responsible_units_source_audit.md](../experiments/retrieval/reports/retrieval/v3/responsible_units_source_audit.md) |
| `reports/retrieval/v3/v1_v3_fair_comparison.md` | [experiments/retrieval/reports/retrieval/v3/v1_v3_fair_comparison.md](../experiments/retrieval/reports/retrieval/v3/v1_v3_fair_comparison.md) |
| `reports/retrieval/v3/v1_v3_version_neutral.md` | [experiments/retrieval/reports/retrieval/v3/v1_v3_version_neutral.md](../experiments/retrieval/reports/retrieval/v3/v1_v3_version_neutral.md) |
| `reports/retrieval/version_neutral/pooling_corrected.md` | [experiments/retrieval/reports/retrieval/version_neutral/pooling_corrected.md](../experiments/retrieval/reports/retrieval/version_neutral/pooling_corrected.md) |
| `reports/retrieval/version_neutral/rebuild_prereqs_check.md` | [experiments/retrieval/reports/retrieval/version_neutral/rebuild_prereqs_check.md](../experiments/retrieval/reports/retrieval/version_neutral/rebuild_prereqs_check.md) |
| `reports/retrieval/version_neutral/rubric_v3_pilot.md` | [experiments/retrieval/reports/retrieval/version_neutral/rubric_v3_pilot.md](../experiments/retrieval/reports/retrieval/version_neutral/rubric_v3_pilot.md) |
| `reports/retrieval/version_neutral/v1_vs_v3.md` | [experiments/retrieval/reports/retrieval/version_neutral/v1_vs_v3.md](../experiments/retrieval/reports/retrieval/version_neutral/v1_vs_v3.md) |

## 검수

[제3자 전문가 AI 검수와 경로 확인 기록](documentation_reorganization_review_2026-09-26.md). 운영 실행·Windows·모델 품질을 재검증한 작업은 아니다.

## 현재 원본이 없는 과거 참조

정적 파일 링크 검사에서 주요 진입 문서는 대상 파일 누락이 없었다. 아래 14개 링크 발생(중복 포함)은 기존 과거 기록에 속하며, 연결 대상이 현재 작업 공간에 없다. 실행 결과·미존재 원본을 새로 만들지 않았다.

| 기록 문서 | 현재 없는 링크 대상 |
|---|---|
| `docs/10_contracts/interfaces/week1/be2_be3_compromise_contract_week1.md` | `be2_be3_week1_agreement_checklist.md` |
| `docs/50_issues/retrieval_evaluation_accuracy_plan.md` | `../../scripts/build_aihub_retrieval_eval_set.py` |
| `experiments/generation/docs/40_delivery/week5/WEEK5_BE3_4_MODEL_SAMPLE50_COMPARISON_REPORT.md` | `../../../../../docs/40_delivery/week4/WEEK4_BE3_INTEGRATED_WEEK3_TO_WEEK4_MODEL_REPORT.md` |
| `experiments/generation/docs/40_delivery/week5/WEEK5_BE3_4_MODEL_SAMPLE50_COMPARISON_REPORT.md` | `../../../../../logs/evaluation/week5/ax4_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_ax4_light.md` |
| `experiments/generation/docs/40_delivery/week5/WEEK5_BE3_4_MODEL_SAMPLE50_COMPARISON_REPORT.md` | `../../../../../logs/evaluation/week5/exaone_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md` |
| `experiments/generation/docs/40_delivery/week5/WEEK5_BE3_4_MODEL_SAMPLE50_COMPARISON_REPORT.md` | `../../../../../logs/evaluation/week5/gemma3_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_gemma3_12b.md` |
| `experiments/generation/docs/40_delivery/week5/WEEK5_BE3_4_MODEL_SAMPLE50_COMPARISON_REPORT.md` | `../../../../../logs/evaluation/week5/gemma4_26b_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_gemma4_26b.md` |
| `experiments/generation/docs/40_delivery/week5/WEEK5_BE3_WEEK4_VS_WEEK5_SAMPLE50_COMPARISON_REPORT.md` | `../../../../../docs/40_delivery/week4/WEEK4_BE3_INTEGRATED_WEEK3_TO_WEEK4_MODEL_REPORT.md` |
| `experiments/generation/docs/40_delivery/week5/WEEK5_BE3_WEEK4_VS_WEEK5_SAMPLE50_COMPARISON_REPORT.md` | `../../../../../logs/evaluation/week5/ax4_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_ax4_light.md` |
| `experiments/generation/docs/40_delivery/week5/WEEK5_BE3_WEEK4_VS_WEEK5_SAMPLE50_COMPARISON_REPORT.md` | `../../../../../logs/evaluation/week5/exaone_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_exaone_3_5_7_8b.md` |
| `experiments/generation/docs/40_delivery/week5/WEEK5_BE3_WEEK4_VS_WEEK5_SAMPLE50_COMPARISON_REPORT.md` | `../../../../../logs/evaluation/week5/gemma3_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_gemma3_12b.md` |
| `experiments/generation/docs/40_delivery/week5/WEEK5_BE3_WEEK4_VS_WEEK5_SAMPLE50_COMPARISON_REPORT.md` | `../../../../../logs/evaluation/week5/gemma4_26b_ctx1024_W5Script_sample50/model_benchmark_candidate_candidate_gemma4_26b.md` |

## 2026-09-26 overview 후속 정리

위 113개 이동 명세는 최초 정리 이력이다. 후속 정리에서 회사 지식 PRD는 `00_overview/company_knowledge_prd.md`로 이동(v1.4)했다. ADR은 Git HEAD b53134a와 현재 코드 기준 v3.0으로 갱신했으며 v2.2 원문은 `90_archive/complaint_system/`에 보존했다. 과거 사용자 시나리오와 검색 기술 선정서도 같은 archive로 옮겼다. `00_overview/prd.md`, `architecture.md`, `company_knowledge_milestones.md` 이동 안내는 제거했고 `company_knowledge_prd.md` 이동 안내는 실제 PRD로 교체했다. overview에는 7개 문서가 남는다.
