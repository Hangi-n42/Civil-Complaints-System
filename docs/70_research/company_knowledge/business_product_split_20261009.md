# 업무 지식 제품 변경과 연구 기록의 분리 — 2026-10-09

제품 변경은 main `2defd05612d8cc8a159fa17ac169a2c532d6b200`에서 분리했으며 원본은 [00ecdc34791ec3192b2e6b66886809cb5e1a4bd0](https://github.com/Hangi-n42/Civil-Complaints-System/tree/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0)에 보존한다. 커밋 단위 선별이 아닌 최종 파일 차이를 사용했다.

기본 검수는 main의 v4에서 v8로 바뀐다. v13은 별도 recipe 선택 경로이고, `reviewed_items`는 UI에서 선택하는 검토 의미 기반 답변 방식이다. 서로 같은 설정이 아니다. v9/v10 검수 및 `source_quotes`/`items` 답변은 미채택 실험 경로이며 기본값으로 승격하지 않는다. `answered`는 응답 형식과 제공 근거 참조 검사 상태이며 의미 정확성이나 업무 요구의 전체 충족을 보증하지 않는다.

## 제품에 보존한 파일

제품 코드 12개, 관련 테스트 17개, 화면 fixture 1개 및 아래 제품 검증 문서·JSON을 유지한다. NLI, semantic_followup, span_binding, support_mechanism 기록은 연구 내용과 실제 제품 수정 검증이 함께 있어 원문 그대로 보존한다. 제외한 연구 문서의 상대 링크만 고정 SHA 원본 링크로 바꾼다.

- [app/api/routers/knowledge.py](../../../app/api/routers/knowledge.py)
- [app/knowledge/autoschema.py](../../../app/knowledge/autoschema.py)
- [app/knowledge/business_changes.py](../../../app/knowledge/business_changes.py)
- [app/knowledge/business_edit.py](../../../app/knowledge/business_edit.py)
- [app/knowledge/business_models.py](../../../app/knowledge/business_models.py)
- [app/knowledge/business_review.py](../../../app/knowledge/business_review.py)
- [app/knowledge/business_run.py](../../../app/knowledge/business_run.py)
- [app/knowledge/business_use.py](../../../app/knowledge/business_use.py)
- [app/knowledge/discovery_profile.py](../../../app/knowledge/discovery_profile.py)
- [app/knowledge/graph_retrieval.py](../../../app/knowledge/graph_retrieval.py)
- [app/knowledge/parsers.py](../../../app/knowledge/parsers.py)
- [app/tests/unit/test_knowledge_business.py](../../../app/tests/unit/test_knowledge_business.py)
- [app/tests/unit/test_knowledge_business_answer_scope.py](../../../app/tests/unit/test_knowledge_business_answer_scope.py)
- [app/tests/unit/test_knowledge_business_changes.py](../../../app/tests/unit/test_knowledge_business_changes.py)
- [app/tests/unit/test_knowledge_business_edit.py](../../../app/tests/unit/test_knowledge_business_edit.py)
- [app/tests/unit/test_knowledge_business_event_repair.py](../../../app/tests/unit/test_knowledge_business_event_repair.py)
- [app/tests/unit/test_knowledge_business_local_review.py](../../../app/tests/unit/test_knowledge_business_local_review.py)
- [app/tests/unit/test_knowledge_business_responsibilities.py](../../../app/tests/unit/test_knowledge_business_responsibilities.py)
- [app/tests/unit/test_knowledge_business_row_answer.py](../../../app/tests/unit/test_knowledge_business_row_answer.py)
- [app/tests/unit/test_knowledge_business_scope_evidence.py](../../../app/tests/unit/test_knowledge_business_scope_evidence.py)
- [app/tests/unit/test_knowledge_business_semantic_edit.py](../../../app/tests/unit/test_knowledge_business_semantic_edit.py)
- [app/tests/unit/test_knowledge_business_separated_review.py](../../../app/tests/unit/test_knowledge_business_separated_review.py)
- [app/tests/unit/test_knowledge_business_source_fields.py](../../../app/tests/unit/test_knowledge_business_source_fields.py)
- [app/tests/unit/test_knowledge_business_tabular_repair.py](../../../app/tests/unit/test_knowledge_business_tabular_repair.py)
- [app/tests/unit/test_knowledge_business_target_boundary.py](../../../app/tests/unit/test_knowledge_business_target_boundary.py)
- [app/tests/unit/test_knowledge_graph_retrieval.py](../../../app/tests/unit/test_knowledge_graph_retrieval.py)
- [docs/70_research/company_knowledge/business_answer_items_20261007.md](../../../docs/70_research/company_knowledge/business_answer_items_20261007.md)
- [docs/70_research/company_knowledge/business_direct_edit_20261008.json](../../../docs/70_research/company_knowledge/business_direct_edit_20261008.json)
- [docs/70_research/company_knowledge/business_direct_edit_20261008.md](../../../docs/70_research/company_knowledge/business_direct_edit_20261008.md)
- [docs/70_research/company_knowledge/business_evidence_parent_boundary_20261007.md](../../../docs/70_research/company_knowledge/business_evidence_parent_boundary_20261007.md)
- [docs/70_research/company_knowledge/business_fact_candidate_responsibilities_20261007.md](../../../docs/70_research/company_knowledge/business_fact_candidate_responsibilities_20261007.md)
- [docs/70_research/company_knowledge/business_finding_lifecycle_20261009.json](../../../docs/70_research/company_knowledge/business_finding_lifecycle_20261009.json)
- [docs/70_research/company_knowledge/business_finding_lifecycle_20261009.md](../../../docs/70_research/company_knowledge/business_finding_lifecycle_20261009.md)
- [docs/70_research/company_knowledge/business_finding_usage_20261009.json](../../../docs/70_research/company_knowledge/business_finding_usage_20261009.json)
- [docs/70_research/company_knowledge/business_finding_usage_20261009.md](../../../docs/70_research/company_knowledge/business_finding_usage_20261009.md)
- [docs/70_research/company_knowledge/business_native_event_repair_20261008.json](../../../docs/70_research/company_knowledge/business_native_event_repair_20261008.json)
- [docs/70_research/company_knowledge/business_native_event_repair_20261008.md](../../../docs/70_research/company_knowledge/business_native_event_repair_20261008.md)
- [docs/70_research/company_knowledge/business_nli_20261009.json](../../../docs/70_research/company_knowledge/business_nli_20261009.json)
- [docs/70_research/company_knowledge/business_nli_20261009.md](../../../docs/70_research/company_knowledge/business_nli_20261009.md)
- [docs/70_research/company_knowledge/business_operating_scope_20261008.json](../../../docs/70_research/company_knowledge/business_operating_scope_20261008.json)
- [docs/70_research/company_knowledge/business_operating_scope_20261008.md](../../../docs/70_research/company_knowledge/business_operating_scope_20261008.md)
- [docs/70_research/company_knowledge/business_repair_retrieval_20261007.md](../../../docs/70_research/company_knowledge/business_repair_retrieval_20261007.md)
- [docs/70_research/company_knowledge/business_repair_retrieval_followup_20261007.md](../../../docs/70_research/company_knowledge/business_repair_retrieval_followup_20261007.md)
- [docs/70_research/company_knowledge/business_resolution_contract_20261009.json](../../../docs/70_research/company_knowledge/business_resolution_contract_20261009.json)
- [docs/70_research/company_knowledge/business_resolution_contract_20261009.md](../../../docs/70_research/company_knowledge/business_resolution_contract_20261009.md)
- [docs/70_research/company_knowledge/business_retrieval_r4_20261007.md](../../../docs/70_research/company_knowledge/business_retrieval_r4_20261007.md)
- [docs/70_research/company_knowledge/business_scope_boundary_20261009.json](../../../docs/70_research/company_knowledge/business_scope_boundary_20261009.json)
- [docs/70_research/company_knowledge/business_scope_boundary_20261009.md](../../../docs/70_research/company_knowledge/business_scope_boundary_20261009.md)
- [docs/70_research/company_knowledge/business_scope_evidence_20261009.json](../../../docs/70_research/company_knowledge/business_scope_evidence_20261009.json)
- [docs/70_research/company_knowledge/business_scope_evidence_20261009.md](../../../docs/70_research/company_knowledge/business_scope_evidence_20261009.md)
- [docs/70_research/company_knowledge/business_selection_repair_20261007.md](../../../docs/70_research/company_knowledge/business_selection_repair_20261007.md)
- [docs/70_research/company_knowledge/business_semantic_edit_20261008.json](../../../docs/70_research/company_knowledge/business_semantic_edit_20261008.json)
- [docs/70_research/company_knowledge/business_semantic_edit_20261008.md](../../../docs/70_research/company_knowledge/business_semantic_edit_20261008.md)
- [docs/70_research/company_knowledge/business_semantic_followup_20261008.json](../../../docs/70_research/company_knowledge/business_semantic_followup_20261008.json)
- [docs/70_research/company_knowledge/business_semantic_followup_20261008.md](../../../docs/70_research/company_knowledge/business_semantic_followup_20261008.md)
- [docs/70_research/company_knowledge/business_service_contract_alignment_20261008.json](../../../docs/70_research/company_knowledge/business_service_contract_alignment_20261008.json)
- [docs/70_research/company_knowledge/business_service_contract_alignment_20261008.md](../../../docs/70_research/company_knowledge/business_service_contract_alignment_20261008.md)
- [docs/70_research/company_knowledge/business_source_fields_20261008.json](../../../docs/70_research/company_knowledge/business_source_fields_20261008.json)
- [docs/70_research/company_knowledge/business_source_fields_20261008.md](../../../docs/70_research/company_knowledge/business_source_fields_20261008.md)
- [docs/70_research/company_knowledge/business_span_binding_comparison_20261008.json](../../../docs/70_research/company_knowledge/business_span_binding_comparison_20261008.json)
- [docs/70_research/company_knowledge/business_span_binding_comparison_20261008.md](../../../docs/70_research/company_knowledge/business_span_binding_comparison_20261008.md)
- [docs/70_research/company_knowledge/business_support_mechanism_20261008.json](../../../docs/70_research/company_knowledge/business_support_mechanism_20261008.json)
- [docs/70_research/company_knowledge/business_support_mechanism_20261008.md](../../../docs/70_research/company_knowledge/business_support_mechanism_20261008.md)
- [docs/70_research/company_knowledge/business_target_boundary_20261009.json](../../../docs/70_research/company_knowledge/business_target_boundary_20261009.json)
- [docs/70_research/company_knowledge/business_target_boundary_20261009.md](../../../docs/70_research/company_knowledge/business_target_boundary_20261009.md)
- [frontend/__tests__/fixtures/knowledgeBusinessReplacement.json](../../../frontend/__tests__/fixtures/knowledgeBusinessReplacement.json)
- [frontend/__tests__/knowledgeBusinessEdit.test.ts](../../../frontend/__tests__/knowledgeBusinessEdit.test.ts)
- [frontend/__tests__/knowledgeBusinessRender.test.ts](../../../frontend/__tests__/knowledgeBusinessRender.test.ts)
- [frontend/components/KnowledgeBusiness.tsx](../../../frontend/components/KnowledgeBusiness.tsx)

## 별도 연구 묶음

다음 파일은 이 제품 PR에 복사하지 않았으며 고정 원본에서 확인한다. 새 연구 PR이나 모델 재실행은 만들지 않는다.

- [app/tests/unit/test_business_clearcheck_diagnostic.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/app/tests/unit/test_business_clearcheck_diagnostic.py)
- [app/tests/unit/test_business_korean_judge_diagnostic.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/app/tests/unit/test_business_korean_judge_diagnostic.py)
- [app/tests/unit/test_business_label_selection.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/app/tests/unit/test_business_label_selection.py)
- [app/tests/unit/test_business_natlogic_diagnostic.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/app/tests/unit/test_business_natlogic_diagnostic.py)
- [app/tests/unit/test_business_permutation_selection.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/app/tests/unit/test_business_permutation_selection.py)
- [app/tests/unit/test_business_qa_diagnostic.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/app/tests/unit/test_business_qa_diagnostic.py)
- [app/tests/unit/test_business_scope_tree_diagnostic.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/app/tests/unit/test_business_scope_tree_diagnostic.py)
- [docs/70_research/company_knowledge/business_clearcheck_20261009.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_clearcheck_20261009.json)
- [docs/70_research/company_knowledge/business_clearcheck_20261009.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_clearcheck_20261009.md)
- [docs/70_research/company_knowledge/business_condition_scope_comparison_20261008.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_condition_scope_comparison_20261008.json)
- [docs/70_research/company_knowledge/business_condition_scope_comparison_20261008.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_condition_scope_comparison_20261008.md)
- [docs/70_research/company_knowledge/business_criterion_review_20261009.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_criterion_review_20261009.json)
- [docs/70_research/company_knowledge/business_criterion_review_20261009.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_criterion_review_20261009.md)
- [docs/70_research/company_knowledge/business_korean_judge_20261009.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_korean_judge_20261009.json)
- [docs/70_research/company_knowledge/business_korean_judge_20261009.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_korean_judge_20261009.md)
- [docs/70_research/company_knowledge/business_label_selection_20261009.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_label_selection_20261009.json)
- [docs/70_research/company_knowledge/business_label_selection_20261009.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_label_selection_20261009.md)
- [docs/70_research/company_knowledge/business_natlogic_20261009.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_natlogic_20261009.json)
- [docs/70_research/company_knowledge/business_natlogic_20261009.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_natlogic_20261009.md)
- [docs/70_research/company_knowledge/business_permutation_selection_20261009.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_permutation_selection_20261009.json)
- [docs/70_research/company_knowledge/business_permutation_selection_20261009.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_permutation_selection_20261009.md)
- [docs/70_research/company_knowledge/business_qa_compare_20261009.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_qa_compare_20261009.json)
- [docs/70_research/company_knowledge/business_qa_compare_20261009.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_qa_compare_20261009.md)
- [docs/70_research/company_knowledge/business_scope_difference_comparison_20261008.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_scope_difference_comparison_20261008.json)
- [docs/70_research/company_knowledge/business_scope_difference_comparison_20261008.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_scope_difference_comparison_20261008.md)
- [docs/70_research/company_knowledge/business_scope_model_comparison_20261008.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_scope_model_comparison_20261008.json)
- [docs/70_research/company_knowledge/business_scope_model_comparison_20261008.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_scope_model_comparison_20261008.md)
- [docs/70_research/company_knowledge/business_scope_tree_20261009.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_scope_tree_20261009.json)
- [docs/70_research/company_knowledge/business_scope_tree_20261009.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_scope_tree_20261009.md)
- [docs/70_research/company_knowledge/business_source_boundary_20261007.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_source_boundary_20261007.md)
- [docs/70_research/company_knowledge/business_source_first_comparison_20261007.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_source_first_comparison_20261007.md)
- [docs/70_research/company_knowledge/business_vitaminc_20261009.json](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_vitaminc_20261009.json)
- [docs/70_research/company_knowledge/business_vitaminc_20261009.md](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/docs/70_research/company_knowledge/business_vitaminc_20261009.md)
- [scripts/compare_business_clearcheck.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/compare_business_clearcheck.py)
- [scripts/compare_business_korean_judge.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/compare_business_korean_judge.py)
- [scripts/compare_business_label_selection.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/compare_business_label_selection.py)
- [scripts/compare_business_natlogic.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/compare_business_natlogic.py)
- [scripts/compare_business_nli.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/compare_business_nli.py)
- [scripts/compare_business_permutation_selection.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/compare_business_permutation_selection.py)
- [scripts/compare_business_qa.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/compare_business_qa.py)
- [scripts/compare_business_scope_tree.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/compare_business_scope_tree.py)
- [scripts/compare_business_vitaminc.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/compare_business_vitaminc.py)
- [scripts/evaluate_passage_selection.py](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/evaluate_passage_selection.py)
- [scripts/patches/hyperclovax_think_eog.patch](https://github.com/Hangi-n42/Civil-Complaints-System/blob/00ecdc34791ec3192b2e6b66886809cb5e1a4bd0/scripts/patches/hyperclovax_think_eog.patch)

## 의존성과 재현 범위

제품 테스트가 공유하는 `test_knowledge_business_scope.py`는 main에 이미 있다. local_review/event_repair/edit/semantic_edit/row_answer helper와 화면 replacement fixture는 이 변경에 함께 포함한다. 제품 테스트는 이번에 제외한 연구 실행기를 import하지 않는다. 기존 main의 평가 실행기와 관련 테스트는 변경하지 않는다.

제품 검증 JSON의 실제 요청·응답, 코드 manifest, 실패 및 기각 경계는 재작성하지 않았다. 기록 안의 로컬 경로와 과거 SHA는 당시 실행의 출처이며 현재 checkout의 파일 위치를 보장하지 않는다. Git 미추적 평가 DB·원본·raw 분포는 기존 작업 공간에 보존되며 Git clone만으로 모든 실험을 재현할 수 없다. 이번 코드 검사와 과거의 제한된 실제 모델 결과를 구분한다. 자동 조건 오류 교정, R05 전체 품질 해결 또는 일반 의미 정확성 향상은 입증하지 않았다.

## 신규 응답의 실행 경계

`business_use.query`는 답변 run을 생성한 뒤 검색 실패, 검색 근거 없음, 최종 답변 응답에 `execution_boundary`를 함께 반환하고 그 run에 저장한다. run 생성 전의 `needs_review`/`no_reviewed_claims`/`no_source_passages`에는 이 필드를 추가하지 않는다.

- `answer_mode`와 `unadopted_answer_mode`는 현재 QA 요청을 나타낸다. `source_quotes`/`items`는 미채택 실험으로 표시한다.
- `answer_contract`는 실제 답변 경로에서 사용한 계약이다. 답변 전에 검색이 실패하거나 근거가 없으면 null이며, 원문 선택 경로가 인용 근거 없이 반환돼 계약을 기록하지 못한 경우에도 null이다.
- `source_review_run_id`, `source_run_review_contract`, `source_run_review_experimental`은 원본 실행 recipe의 검수 이력이다. v9/v10을 미채택 실험으로 표시하지만 현재 QA에서 그 검수를 새로 실행했다는 뜻이 아니다. recipe에 계약이 없는 과거 기록은 null로 유지한다.
- `review_provenance_scope=source_run_recipe_not_all_snapshot_assessments`는 단일 recipe가 snapshot의 모든 assessment 계약을 대표하지 않는다는 범위를 명시한다. 개별 검수 이력을 덮어쓰지 않는다.
- `status_semantics`는 `answered`와 의미 정확성·요구 전체 충족이 다르다는 설명이다. 실험 표시 false를 품질 검증 true로 해석하지 않는다.

과거 run/snapshot을 변경하거나 새 승인을 요구하지 않는다. 기본 검수·답변 선택도 이 메타데이터 추가로 바뀌지 않는다.

## 분리 무결성 검사

제품 원본 69개 중 62개는 원본 SHA와 바이트 단위로 같다. 추가 수정은 응답 경계(`business_use.py`), 신규 v8 실행·답변 경계 검사(테스트 2개), 제외 연구 문서를 가리키는 링크 6개(문서 4개)다. 검증 JSON 16개는 모두 원본과 같다. 이 목록 문서 1개를 더해 최종 변경은 70개 파일이다. 제외한 44개 파일은 새 제품 트리에 없으며 관련 제품 테스트의 helper import 대상과 상대 문서 링크는 모두 존재한다.

## 최종 제품 트리 검사 — 2026-10-09

- `python -m pytest app/tests/unit/test_knowledge_business*.py app/tests/unit/test_knowledge_graph_retrieval.py -q --tb=short`: 관련 백엔드 17개 파일, **351 passed**, 255.66초. 기본 v8 신규 실행, 부분 편집·재검수·승인 무효화, 후보/원문/근거 경계, 기본·선택 답변과 실험 표시를 포함한다.
- `vitest run __tests__/knowledgeBusinessEdit.test.ts __tests__/knowledgeBusinessRender.test.ts`: **10 passed**. 편집 요청·재검수 선택·대체 후보 표시·공개 질문에 연결된 답변 선택을 검사했다.
- `tsc --noEmit --incremental false` 및 변경한 화면·테스트 3개 파일의 ESLint: 통과.
- 선택 파일·JSON 동일성, 공유 helper·fixture 존재, 상대 문서 링크, `git diff --cached --check`: 통과.

Python은 기존 프로젝트 `.venv`를, Node는 설치된 Codex runtime과 기존 frontend dependency를 사용했다. 모의 모델 응답과 합성 fixture를 사용하는 코드 검사이며 신규 실제 모델 호출·추출·전체 평가·실사용자 시험·브라우저 수동 검수·병합·배포는 수행하지 않았다.
