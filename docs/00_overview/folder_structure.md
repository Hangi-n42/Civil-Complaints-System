# 폴더 구조 설계 문서 (최종본)

문서 버전: v2.0 (8주 구현 기준)  
작성일: 2026-03-27  
기준 문서: [PRD v1.2](prd.md), [WBS v3.1](wbs_8weeks_v2_updated.md), [MVP 범위](mvp_scope.md)  
목적: Week 1~8 전체 실행 과정에서 팀의 완전성, 안정성, 추적 가능성을 보장하는 디렉터리 구조 확정

---

## 1. 설계 원칙 (Week 1~8 반영)

### 1.1 핵심 원칙
- **기능 축 분리**: ingestion / structuring / retrieval / generation / ui 경계는 절대 유지
- **데이터 생명주기 관리**: raw → processed → indexed → evaluated 단계별 분리 저장
- **마일스톤별 산출물 추적**: M1(W2) → M2(W4) → M3(W6) → M4(W8) 각 게이트별 명확한 폴더 위치
- **평가/실험 과학화**: 매주 측정 결과, 모델 벤치마크, ablation 결과를 재현 가능하게 저장
- **운영의 단순성**: 초기 구축 후 팀 전체가 같은 위치를 자동으로 참고하도록 경로 고정

### 1.2 W2 종료 시점의 경험 반영
- 구조화 결과(50건+)가 어디 저장되는지 명확해야 인덱싱/검색 팀이 효율적
- 평가 지표(F1, precision, recall)가 자동으로 리포트되지 않으면 주간 진행률 추적 어려움
- API 요청/응답 로그가 없으면 후반 버그 재현 불가능
- 계약 문서(schema, interface)가 분산되면 팀 간 동기화 누락 발생

### 1.3 W3~W8 예상 산출물 기준
| 주차 | 주요 산출물 | 저장 위치 |
|-----|----------|---------|
| W2 마감 | 구조화 결과셋 (50건), 평가 리포트 | `data/structured/`, `reports/` |
| W3 마감 | 인덱싱 완료 (500건), 검색 메트릭, 모델 벤치마크 | `data/indexed/`, `logs/evaluation/` |
| W4 마감 | 단일 RAG baseline, citation 정합성 리포트 | `logs/evaluation/week4/` |
| W5 마감 | 길이 라우팅 실험, ablation #1 | `logs/evaluation/week5/` |
| W6 마감 | 주제/복합 분기, unified schema 검증 | `logs/evaluation/week6/` |
| W8 마감 | 발표자료, 최종 코드, README, 평가보고서 | `artifacts/`, 프로젝트 루트 |

---

## 2. 최종 완성형 폴더 구조 (8주차 기준)

```text
AI-Civil-Affairs-Systems/
│
├─ README.md                          [프로젝트 개요 & 빠른 시작 가이드]
├─ .env.example                       [환경변수 템플릿]
├─ .gitignore                         [Git 무시 규칙]
├─ requirements.txt                   [Python 의존성]
├─ pyproject.toml                     [선택: 패키지 메타정보]
│
├─ 📂 docs/                           [모든 기획/설계/운영 문서]
│  ├─ README.md                       [문서 인덱스]
│  ├─ 00_overview/                    [프로젝트 전략 문서]
│  │  ├─ prd.md                       [v1.2 최종 PRD]
│  │  ├─ mvp_scope.md                 [MVP 범위 & Out of Scope]
│  │  ├─ dev_stack.md                 [기술스택 확정안]
│  │  ├─ folder_structure.md          [이 문서]
│  │  └─ wbs_8weeks_v2_updated.md     [v3.1 WBS & 마일스톤]
│  │
│  ├─ 10_contracts/                   [팀 간 역할/인터페이스 계약]
│  │  ├─ api/
│  │  │  └─ api_spec.md               [API 엔드포인트 명세]
│  │  ├─ schema/
│  │  │  ├─ schema_contract.md        [JSON 스키마 정의]
│  │  │  └─ (실제 JSON 스키마는 schemas/ 에 저장)
│  │  └─ interfaces/                  [주차별 인터페이스 정의]
│  │     ├─ week2/
│  │     │  ├─ README.md
│  │     │  ├─ week2_common_interface.md
│  │     │  ├─ week2_be1_interface.md
│  │     │  ├─ week2_be2_interface.md
│  │     │  ├─ week2_be3_interface.md
│  │     │  └─ week2_fe_interface.md
│  │     ├─ week3/
│  │     │  ├─ README.md
│  │     │  ├─ week3_common_interface.md
│  │     │  ├─ week3_be1_interface.md
│  │     │  ├─ week3_be2_interface.md
│  │     │  ├─ week3_be3_interface.md
│  │     │  └─ week3_fe_interface.md
│  │     ├─ be1_be2_interface.md       [BE1-BE2 협업 계약]
│  │     ├─ be2_be3_interface.md       [BE2-BE3 협업 계약]
│  │     └─ be3_fe_unified_spec.md     [통합 응답 스키마]
│  │
│  ├─ 20_domains/                     [도메인별 설계 & 기술 문서]
│  │  ├─ ingestion_structuring/
│  │  │  ├─ README.md
│  │  │  ├─ data_cleaning_rules.md    [정제 규칙, PII 마스킹]
│  │  │  ├─ ner_entity_labels.md      [엔티티 태그 정의]
│  │  │  └─ structure_validation.md   [스키마 검증 규칙]
│  │  │
│  │  ├─ retrieval/
│  │  │  ├─ README.md
│  │  │  ├─ retrieval_strategy.md     [검색 전략, 시맨틱 vs 필터]
│  │  │  ├─ indexing_plan.md          [인덱싱 파이프라인 설계]
│  │  │  ├─ search_implementation.md  [검색 구현 상세]
│  │  │  ├─ metadata_filter_schema.md [메타필터 정의]
│  │  │  ├─ embedding_comparison.md   [임베딩 모델 비교]
│  │  │  ├─ vectordb_comparison.md    [VectorDB (ChromaDB vs FAISS)]
│  │  │  └─ ollama_setup_note.md      [Ollama 설치/운영]
│  │  │
│  │  └─ generation/
│  │     ├─ README.md
│  │     ├─ single_rag_baseline.md    [단일 RAG 설계]
│  │     ├─ adaptive_rag_design.md    [적응형 RAG (길이/주제/복합 분기)]
│  │     ├─ prompt_templates.md       [프롬프트 템플릿 정의]
│  │     ├─ json_parsing_strategy.md  [JSON 파싱 & 재시도 전략]
│  │     └─ citation_extraction.md    [근거 인용 추출]
│  │
│  ├─ 30_manuals/                     [팀 역할별 실행 나침반]
│  │  ├─ be1_manual.md                [BE1 주간 체크리스트 & 운영 가이드]
│  │  ├─ be2_manual.md                [BE2 주간 체크리스트 & 운영 가이드]
│  │  ├─ be3_manual.md                [BE3 주간 체크리스트 & 운영 가이드]
│  │  └─ fe_manual.md                 [FE 주간 체크리스트 & 운영 가이드]
│  │
│  └─ 40_delivery/                    [마일스톤별 전달 & 리포트]
│     ├─ README.md                    [전달 물량 인덱스]
│     ├─ week1/
│     │  └─ README.md                 [W1 이슈, 산출물, 회고]
│     ├─ week2/
│     │  ├─ README.md                 [W2 이슈 인덱스, M1 Gate 증빙]
│     │  ├─ be1_diff_checklist.md     [BE1 구조화 품질 점검표]
│     │  └─ be2_chromadb_filter_check.md [BE2 필터 검증보고]
│     ├─ week3/
│     │  ├─ README.md                 [W3 미션, 벤치마크 계획]
│     │  ├─ model_benchmark_protocol.md [LLM 벤치마크 실행 규격]
│     │  ├─ benchmark_case_expansion_rules.md [평가셋 확장 규칙]
│     │  └─ model_test_assets/
│     │     ├─ evaluation_set.json    [500건 평가셋 (W3)]
│     │     └─ ground_truth.json      [정답셋]
│     ├─ week4/
│     │  └─ README.md                 [W4 단일 RAG baseline 게이트]
│     ├─ week5/
│     │  └─ README.md                 [W5 길이 라우팅 ablation]
│     ├─ week6/
│     │  └─ README.md                 [W6 주제/복합 라우팅 & unified schema]
│     ├─ demo/
│     │  ├─ scenario_1_road_safety.json
│     │  ├─ scenario_2_water_management.json
│     │  └─ scenario_3_construction.json
│     └─ week8/
│        └─ README.md                 [W8 최종 발표, 평가]
│
├─ 📂 app/                            [애플리케이션 소스 코드]
│  ├─ __init__.py
│  ├─ core/
│  │  ├─ __init__.py
│  │  ├─ config.py                    [설정 로딩 (base/local/models.yaml)]
│  │  ├─ logging.py                   [공통 로거 (PII 마스킹)]
│  │  ├─ exceptions.py                [커스텀 예외 정의]
│  │  └─ utils.py                     [범용 유틸리티]
│  │
│  ├─ api/                            [FastAPI 서버]
│  │  ├─ __init__.py
│  │  ├─ main.py                      [앱 진입점, 라우터 등록]
│  │  ├─ error_utils.py               [에러 래핑 & 표준화]
│  │  ├─ routers/
│  │  │  ├─ __init__.py
│  │  │  ├─ ingest.py                 [POST /ingest]
│  │  │  ├─ structure.py              [POST /structure]
│  │  │  ├─ index.py                  [POST /index]
│  │  │  ├─ search.py                 [POST /search]
│  │  │  ├─ qa.py                     [POST /qa]
│  │  │  └─ health.py                 [GET /health]
│  │  └─ schemas/
│  │     ├─ __init__.py
│  │     ├─ ingest.py                 [CivilCaseInput]
│  │     ├─ structure.py              [StructuredCivilCase]
│  │     ├─ search.py                 [SearchRequest, SearchResult]
│  │     └─ qa.py                     [QARequest, QAResponse]
│  │
│  ├─ ingestion/
│  │  ├─ __init__.py
│  │  ├─ service.py                   [Ingestion 오케스트레이션]
│  │  ├─ loaders/
│  │  │  ├─ __init__.py
│  │  │  ├─ csv_loader.py
│  │  │  ├─ json_loader.py
│  │  │  └─ manual_input.py
│  │  ├─ preprocess/
│  │  │  ├─ __init__.py
│  │  │  ├─ cleaner.py                [정제 규칙]
│  │  │  ├─ pii_masker.py             [PII 마스킹]
│  │  │  └─ deduplicator.py           [중복 탐지]
│  │  └─ validators/
│  │     ├─ __init__.py
│  │     └─ input_validator.py        [입력 검증]
│  │
│  ├─ structuring/
│  │  ├─ __init__.py
│  │  ├─ service.py                   [Structuring 오케스트레이션]
│  │  ├─ extractors/
│  │  │  ├─ __init__.py
│  │  │  ├─ four_element_extractor.py [4요소 추출]
│  │  │  └─ ner_extractor.py          [NER 추출]
│  │  ├─ validators/
│  │  │  ├─ __init__.py
│  │  │  └─ schema_validator.py       [스키마 검증]
│  │  └─ postprocess/
│  │     ├─ __init__.py
│  │     └─ rule_corrector.py         [룰 기반 후처리]
│  │
│  ├─ retrieval/
│  │  ├─ __init__.py
│  │  ├─ service.py                   [Retrieval 오케스트레이션]
│  │  ├─ entity_labels.py             [엔티티 라벨 상수]
│  │  ├─ embeddings/
│  │  │  ├─ __init__.py
│  │  │  └─ embedder.py               [BGE-m3 임베더]
│  │  ├─ vectorstores/
│  │  │  ├─ __init__.py
│  │  │  ├─ chromadb_store.py         [ChromaDB 래퍼]
│  │  │  └─ faiss_store.py            [FAISS 래퍼 (선택)]
│  │  └─ search/
│  │     ├─ __init__.py
│  │     ├─ retriever.py              [시맨틱 검색]
│  │     └─ filters.py                [메타데이터 필터]
│  │
│  ├─ generation/
│  │  ├─ __init__.py
│  │  ├─ service.py                   [Generation 오케스트레이션]
│  │  ├─ llm/
│  │  │  ├─ __init__.py
│  │  │  ├─ ollama_client.py          [Ollama 호출 클라이언트]
│  │  │  └─ model_manager.py          [모델 관리 (로드/언로드)]
│  │  ├─ prompts/
│  │  │  ├─ __init__.py
│  │  │  ├─ template_factory.py       [프롬프트 템플릿 생성기]
│  │  │  ├─ single_rag.txt            [단일 RAG 프롬프트]
│  │  │  ├─ adaptive_rag.txt          [적응형 RAG 프롬프트]
│  │  │  └─ components.txt            [공통 컴포넌트]
│  │  ├─ parsing/
│  │  │  ├─ __init__.py
│  │  │  ├─ json_parser.py            [JSON 파싱]
│  │  │  └─ retry_handler.py          [재시도 전략]
│  │  ├─ citation/
│  │  │  ├─ __init__.py
│  │  │  └─ citation_builder.py       [근거 인용 추출]
│  │  └─ validators/
│  │     ├─ __init__.py
│  │     └─ response_validator.py     [응답 검증]
│  │
│  ├─ ui/
│  │  ├─ __init__.py
│  │  ├─ Home.py                      [Streamlit 메인(민원 큐/워크벤치/검색/QA)]
│  │  ├─ pages/
│  │  │  └─ __init__.py               [예비 폴더(현재 미사용)]
│  │  ├─ components/
│  │  │  ├─ __init__.py
│  │  │  └─ search_ui.py              [검색/QA UI + 상태배너 + citations/limitations 렌더링]
│  │  └─ services/
│  │     ├─ __init__.py
│  │     ├─ search_service.py         [API 호출/응답 정규화/오류 메시지]
│  │     ├─ ui_case_adapter.py        [UI용 케이스 어댑터]
│  │     └─ retrieval_parser.py       [검색 결과 파서/변환]
│  │
│  └─ tests/
│     ├─ __init__.py
│     ├─ conftest.py                  [Pytest 고정장치]
│     ├─ unit/
│     │  ├─ __init__.py
│     │  ├─ test_ingestion.py
│     │  ├─ test_structuring.py
│     │  ├─ test_retrieval.py
│     │  ├─ test_generation.py
│     │  └─ test_ui.py
│     ├─ integration/
│     │  ├─ __init__.py
│     │  ├─ test_e2e_ingest_structure.py
│     │  ├─ test_e2e_index_search.py
│     │  ├─ test_e2e_qa.py
│     │  └─ test_api_contract.py
│     └─ fixtures/
│        ├─ __init__.py
│        ├─ sample_cases.json
│        ├─ mock_queries.json
│        └─ expected_outputs.json
│
├─ 📂 data/                           [데이터 생명주기별 저장]
│  ├─ raw/
│  │  └─ README.md                    [원본 데이터 (AIHub, 수동 입력)]
│  │
│  │
│  ├─ indexed/
│  │  ├─ chromadb/                    [ChromaDB 벡터스토어]
│  │  │  ├─ civil_cases_v1/           [Week3 500건 인덱싱]
│  │  │  └─ civil_cases_v2/           [선택: 최적화된 버전]
│  │  ├─ faiss/                       [FAISS 인덱스 (선택)]
│  │  └─ README.md
│  │
│  ├─ models/                         [체크포인트 & 전학습 모델]
│  │  ├─ embeddings/
│  │  │  └─ bge-m3/                   [BGE-m3 모델 캐시]
│  │  ├─ llm/
│  │  │  ├─ qwen2.5:7b-instruct/      [Qwen 모델 (Ollama)]
│  │  │  └─ qwen2.5:3b-instruct/      [OOM 폴백 모델]
│  │  └─ adapters/                    [선택: LoRA 어댑터]
│  │
│  └─ evaluation_sets/
│     ├─ week3_500_cases.json        [500건 평가셋]
│     ├─ week3_ground_truth.json     [정답셋]
│     ├─ difficult_cases.json        [난이도 높은 케이스]
│     └─ README.md
│
├─ 📂 schemas/                        [JSON 스키마 정의 (계약서)]
│  ├─ README.md
│  ├─ civil_case.schema.json         [구조화된 민원 스키마]
│  ├─ search_result.schema.json      [검색 결과 스키마]
│  └─ qa_response.schema.json        [QA 응답 스키마]
│
├─ 📂 configs/                        [환경 설정]
│  ├─ base.yaml                      [공통 기본 설정]
│  ├─ local.yaml                     [로컬 머신 설정]
│  ├─ models.yaml                    [모델/임베더/VectorDB 설정]
│  ├─ week3_model_benchmark.yaml    [W3 벤치마크 설정]
│  └─ adaptive_rag_config.yaml       [W5+ Adaptive RAG 라우팅 설정]
│
├─ 📂 logs/                           [실행 로그 & 평가 결과]
│  ├─ api/
│  │  ├─ requests_w3.log            [API 요청/응답 로그]
│  │  └─ errors_w3.log              [에러 로그]
│  │
│  ├─ pipeline/
│  │  ├─ ingest_w2.log
│  │  ├─ structure_w2.log
│  │  ├─ indexing_w3.log
│  │  └─ ...
│  │
│  └─ evaluation/
│     ├─ week2/
│     │  ├─ structuring_metrics_w2.json    [F1, Precision, Recall]
│     │  └─ validation_report_w2.json
│     ├─ week3/
│     │  ├─ retrieval_metrics_w3.json     [Recall@K, nDCG@K]
│     │  ├─ indexing_benchmark_w3.json    [처리량, 시간]
│     │  ├─ model_benchmark_aihub.json
│     │  ├─ model_benchmark_exaone3.5.json
│     │  ├─ model_benchmark_gemma3.json
│     │  ├─ model_benchmark_phi4_mini.json
│     │  └─ model_benchmark_report_final.json [5개 모델 비교]
│     ├─ week4/
│     │  ├─ single_rag_baseline.json      [citation 정합성 등]
│     │  └─ qa_generation_metrics_w4.json
│     ├─ week5/
│     │  ├─ ablation_length_routing.json
│     │  └─ adaptive_rag_metrics_w5.json
│     ├─ week6/
│     │  ├─ ablation_topic_routing.json
│     │  ├─ ablation_multi_request.json
│     │  └─ unified_schema_validation_w6.json
│     └─ performance_comparison.json   [baseline vs adaptive]
│
├─ 📂 reports/                        [주간 회고 & 리포트]
│  ├─ README.md                      [리포트 인덱스]
│  ├─ WEEK1_SUMMARY.md
│  ├─ WEEK2_FIXES_SUMMARY.md         [심각도 이슈 5개 수정사항]
│  ├─ WEEK2_FINAL_REPORT.md
│  ├─ WEEK3_BENCHMARK_SUMMARY.md     [모델 벤치마크 결과 요약]
│  ├─ WEEK4_RAG_BASELINE_REPORT.md
│  ├─ WEEK5_ADAPTIVE_RAG_ABLATION.md
│  ├─ WEEK6_UNIFIED_SCHEMA_VALIDATION.md
│  └─ WEEK8_DELIVERY.md              [최종 평가/회고]
│
├─ 📂 artifacts/                      [발표/데모/최종 산출물]
│  ├─ demo/
│  │  ├─ scenario_screenshots/       [데모 스크린샷]
│  │  ├─ demo_script.md              [발표 시연 대본]
│  │  └─ demo_data/
│  │     ├─ scenario_1_road_safety.json
│  │     ├─ scenario_2_water_management.json
│  │     └─ scenario_3_construction.json
│  │
│  ├─ slides/
│  │  ├─ presentation.pptx           [최종 발표 자료]
│  │  └─ technical_deep_dive.pptx    [기술 상세 설명]
│  │
│  ├─ figures/
│  │  ├─ architecture_diagram.png
│  │  ├─ pipeline_flow.png
│  │  └─ model_benchmark_results.png
│  │
│  └─ final_delivery/
│     ├─ README.md                   [최종 배포 가이드]
│     ├─ ARCHITECTURE.md             [시스템 아키텍처]
│     ├─ DEPLOYMENT.md               [배포 & 운영 가이드]
│     ├─ API_REFERENCE.md            [API 완전 레퍼런스]
│     └─ TROUBLESHOOTING.md          [문제해결 가이드]
│
├─ 📂 scripts/                        [실행 & 평가 스크립트]
│  ├─ __init__.py
│  │
│  ├─ ✅ 구현 완료 (W2)
│  │  ├─ run_api.py                  [FastAPI 서버 시작]
│  │  ├─ run_ui.py                   [Streamlit UI 시작]
│  │  ├─ run_ingest_demo.py          [데이터 수집 데모]
│  │  └─ run_structure_demo.py       [구조화 데모]
│  │
│  ├─ 🔨 W3 구현중
│  │  ├─ build_index.py              [500건 인덱싱 스크립트]
│  │  ├─ test_search.py              [검색 기능 테스트]
│  │  ├─ run_week3_model_benchmark.py [모델 벤치마크 실행]
│  │  └─ generate_week3_benchmark_cases_500.py [평가셋 생성]
│  │
│  ├─ 📊 평가/지표 스크립트
│  │  ├─ evaluate_structuring.py     [F1, Precision, Recall]
│  │  ├─ evaluate_retrieval.py       [Recall@K, nDCG@K, latency]
│  │  ├─ evaluate_qa.py              [citation 정합성, 답변 품질]

│  │
│  ├─ 🧪 유틸리티
│  │  ├─ data_profiling.py           [데이터 분석]
│  │  ├─ check_chromadb_filters.py   [필터 검증]
│  │  ├─ monitor_performance.py      [성능 모니터링]
│  │  └─ export_results.py           [결과 내보내기]
│  │
│  └─ 📝 문서 생성
│     ├─ generate_manual_sample_list.py
│     └─ generate_week2_delivery_samples.py
│
└─ 📂 civil/                          [Python 가상환경]
   ├─ pyvenv.cfg
   ├─ Scripts/                        [Windows]
   ├─ Lib/
   └─ include/

```

---

## 3. 핵심 설계 결정 (W1~W8 기준)

### 3.1 데이터 폴더 전략

**원칙**: 데이터는 **생명주기별로 분리**하여 저장한다.

| 폴더 | 용도 | 소유 | 초기화 | 예시 |
|-----|------|-----|------|------|
| `data/raw/` | 원본 민원(AIHub, 수동) | 입력 | 프로젝트 시작 한 번 | 1000건 원본 |
| `data/processed/weekX/` | 정제/구조화 결과 | W2 BE1 | 주차별 | structured_cases_50.json (W2) |
| `data/indexed/chromadb/` | 벡터 저장소 | W3 BE2 | W3 중 한 번 | 500건 인덱싱 (W3) |
| `data/models/` | 체크포인트 & 가중치 | 초기 | 필요시 | BGE-m3, Qwen 모델 |
| `data/evaluation_sets/` | 벤치마크용 평가셋 | W3 BE1 | W3 중 | 500건 ground_truth |

**이점**:
- 실시간으로 "현재 상태"를 파악 가능 (심지어 중간에 오류 발생해도 이전 단계 결과 재사용)
- 데이터 용량 폭증 예측 가능 (structured 50건 → indexed 500건 → 평가 반복 시 × N)
- 팀 간 협업 시 "어디서 입력을 받는가" 명확

### 3.2 로그 & 평가 폴더 전략

**원칙**: 평가 결과는 **주차별 + 주제별** 폴더로 재현 가능하게 저장한다.

```
logs/evaluation/
├─ week2/
│  ├─ structuring_metrics_w2.json    ← F1, P, R for each field
│  └─ validation_report_w2.json
├─ week3/
│  ├─ model_benchmark_aihub.json     ← 개별 모델 결과
│  ├─ model_benchmark_exaone3.5.json
│  └─ model_benchmark_report_final.json ← 5개 통합 비교
├─ week4/
│  ├─ single_rag_baseline.json       ← citation, answer quality
│  └─ qa_generation_metrics_w4.json
├─ week5/
│  └─ ablation_length_routing.json   ← routing on/off 비교
├─ week6/
│  ├─ ablation_topic_routing.json
│  ├─ ablation_multi_request.json
│  └─ unified_schema_validation_w6.json
└─ week7/
   └─ performance_comparison.json    ← baseline vs adaptive
```

**이점**:
- ablation 실험 재반복 필요 시 이전 수치 즉시 비교
- 리포트(Markdown)와 데이터(JSON) 동시 저장으로 시각화 + 원본 데이터 모두 추적

### 3.3 계약 & 인터페이스 폴더 전략

**원칙**: 각 주차마다 **팀 간 협업 약속을 명문화**하여 저장한다.

```
docs/10_contracts/interfaces/
├─ week2/
│  ├─ week2_common_interface.md      ← snake_case, ISO-8601 등
│  ├─ week2_be1_interface.md         ← CivilCaseInput/StructuredCivilCase
│  ├─ week2_be2_interface.md
│  ├─ week2_be3_interface.md
│  └─ week2_fe_interface.md
├─ week3/
│  ├─ week3_common_interface.md      ← IndexRequest, SearchRequest, SearchResult
│  └─ ...
└─ (추후 week4, week5, ...)
```

**이점**:
- "BE1이 출력한 JSON 필드명이 뭐였지?"라는 질문 원천 차단
- 새 팀원 온보딩 시 해당 주의 계약만 읽으면 됨
- 인터페이스 변경 이력(버전)을 명확히 추적 가능

### 3.4 스크립트 폴더 전략

**원칙**: 스크립트는 **용도별 + 상태별**로 구분한다.

| 카테고리 | 스크립트 | 상태 | 완성도 |
|---------|---------|------|--------|
| 서버 실행 | `run_api.py`, `run_ui.py` | ✅ W2 | 완성 |
| 데이터 처리 | `run_ingest_demo.py`, `run_structure_demo.py` | ✅ W2 | 완성 |
| 인덱싱 | `build_index.py`, `test_search.py` | 🔨 W3 | 진행중 |
| 벤치마크 | `run_week3_model_benchmark.py` | 🔨 W3 | 진행중 |
| 평가 | `evaluate_structuring.py`, `evaluate_retrieval.py`, `evaluate_qa.py` | 📊 | 단계적 |
| 유틸 | `check_chromadb_filters.py`, `monitor_performance.py` | 🧪 | 보조 |

**이점**:
- 어느 팀원이라도 "W3 모델 벤치마크 어떻게 돌려?" → `scripts/run_week3_model_benchmark.py` 즉시 찾음
- 평가 스크립트는 **매주 새로 만드는 것이 아니라, 재사용/연장형**으로 구조화
- 통합 테스트 스크립트 (`run_e2e_*.py`)와 분석 스크립트 명확히 구분

### 3.5 아티팩트 폴더 전략 (W7~W8)

**원칙**: 발표/데모/배포 산출물을 **구분된 폴더**에서 관리한다.

```
artifacts/
├─ demo/
│  ├─ demo_script.md                 ← "이 순서로 시연" 대본
│  ├─ scenario_screenshots/          ← 스크린샷 모음
│  └─ demo_data/                     ← 공개용 샘플 데이터
├─ slides/
│  ├─ presentation.pptx              ← 최종 발표 자료
│  └─ technical_deep_dive.pptx       ← 기술 상세
├─ figures/
│  ├─ architecture_diagram.png       ← 시스템 구조도
│  └─ pipeline_flow.png              ← 데이터 흐름
└─ final_delivery/
   ├─ README.md
   ├─ DEPLOYMENT.md                  ← "이렇게 배포하세요"
   ├─ API_REFERENCE.md               ← 모든 엔드포인트
   └─ TROUBLESHOOTING.md             ← 문제해결
```

**이점**:
- 발표 당일 "프레젠테이션 어디 있어?"라는 혼란 제거
- 외부 배포 시 `artifacts/final_delivery/`만 제공하는 패키징 가능
- 추후 포트폴리오 관리 시 여기서만 수집

---

## 4. 주차별 산출물 매핑 (W1~W8)

| 주차 | 핵심 산출물 경로 | 소유 담당 | 다음 단계 입력 |
|-----|-----------------|---------|--------------|
| **W2** | `data/processed/week2/structured_cases_50.json`<br/>`logs/evaluation/week2/structuring_metrics_w2.json` | BE1 | BE2가 W3 인덱싱 시 입력 |
| **W3** | `data/indexed/chromadb/civil_cases_v1/`<br/>`logs/evaluation/week3/model_benchmark_report_final.json` | BE2/BE3 | BE3가 W4 RAG 구현 시 검색 결과 이용 |
| **W4** | `logs/evaluation/week4/single_rag_baseline.json` | BE3 | W5+ ablation 비교 기준선 |
| **W5** | `logs/evaluation/week5/ablation_length_routing.json` | BE2/BE3 | W6 주제 라우팅 설계 시 참고 |
| **W8** | `artifacts/slides/presentation.pptx`<br/>`artifacts/final_delivery/README.md` | 팀 전체 | 졸업작품 제출 |

---

## 5. 팀별 주요 폴더 책임도

| 역할 | 주 소유 | 협업 | 주의사항 |
|-----|--------|------|---------|
| **BE1** | `app/ingestion/`, `app/structuring/`, `data/processed/`, `logs/evaluation/week2-7/` | BE2, BE3 | 평가 스크립트는 BE1이 관리, 타팀은 `.py` 호출만 |
| **BE2** | `app/retrieval/`, `data/indexed/`, `scripts/build_index.py` | BE1, BE3 | 인덱싱 완료 후 `data/indexed/` 상태 정기 보고 |
| **BE3** | `app/api/`, `app/generation/`, `configs/` | BE1, BE2, FE | API 응답 스키마는 절대 변경 금지 (계약 준수) |
| **FE** | `app/ui/`, `artifacts/demo/` | BE3 (API 연동) | 데모 시나리오는 `artifacts/demo/scenario_X.json`에 저장 |

---

## 6. 필수 초기 설정 파일

### 6.1 `.env.example`
```bash
# API
API_HOST=127.0.0.1
API_PORT=8000

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b-instruct

# VectorDB
VECTORSTORE_TYPE=chromadb
CHROMADB_PATH=./data/indexed/chromadb

# Logging
LOG_LEVEL=INFO
LOG_DIR=./logs

# Data
DATA_RAW_PATH=./data/raw
DATA_PROCESSED_PATH=./data/processed
```

### 6.2 `configs/base.yaml`
```yaml
project:
  name: "AI-Civil-Affairs-Systems"
  version: "1.0"

ingestion:
  pii_masking_enabled: true
  deduplication_threshold: 0.95

structuring:
  model: "llama2"
  confidence_threshold: 0.7

retrieval:
  embedder: "bge-m3"
  vectorstore: "chromadb"
  top_k: 5

generation:
  llm_model: "qwen2.5:7b-instruct"
  max_tokens: 1024
  temperature: 0.7

evaluation:
  baseline_f1_threshold: 0.72
  recall_at_5_threshold: 0.75
```

---

## 7. 주의사항 & 운영 규칙

### 7.1 절대 금지 사항
- ❌ `data/raw/`에 구조화 결과 저장 금지 (생명주기 혼란)
- ❌ 개인 로컬 폴더에 중간 결과 저장 후 GitHub 미동기 금지
- ❌ 로그 파일을 `.gitignore` 없이 커밋 금지 (리포지토리 오염)
- ❌ `logs/evaluation/` 폴더 삭제 금지 (이력 추적 불가)

### 7.2 거버넌스
- **주차 시작**: 새 폴더 `logs/evaluation/weekX/` 생성 + README 추가
- **주차 중**: 결과 저장 경로를 docs의 계약 문서에 명시
- **주차 종료**: 리포트(JSON + Markdown) 함께 저장
- **마일스톤 종료**: `reports/WEEKX_FINAL_REPORT.md` 작성 + 팀 리뷰

### 7.3 백업 & 복구
- `data/indexed/chromadb*/`은 **주 1회 백업** (500건 인덱스 재구성 비용)
- `logs/evaluation/`은 **일 1회 자동 커밋** (Git 히스토리로 추적)
- `configs/` 변경은 **Pull Request** 필수 (환경 실수 방지)

---

## 8. 확장성 및 미래 대비

### 8.1 W8 이후 운영 모드
- 모델 주기적 갱신: `data/models/` 버전 관리
- 새로운 민원 데이터 추가: `data/raw/` → `data/processed/weekX/` 자동화
- CI/CD 파이프라인 자동화: `scripts/` 기반

### 8.2 대규모 데이터 전환 (졸업 후 운영)
- `data/indexed/chromadb/` → PostgreSQL/Elasticsearch 전환 시에도 폴더 이름 유지
- `logs/evaluation/` 구조 유지 → 이전 데이터와의 비교 분석 가능

---

## 9. 결론

**핵심 설계 원칙**:
1. **기능 축 분리** (ingestion/structuring/retrieval/generation/ui)
2. **생명주기별 데이터 관리** (raw → processed → indexed → evaluated)
3. **주차별 산출물 추적** (logs/evaluation/weekX/ 자동화)
4. **계약 문서화** (interfaces/weekX/ 인터페이스 명문화)
5. **발표 자료 분리** (artifacts/로 최후 배포 준비)

이 구조로 **4인 팀이 8주 동안 혼란 없이 협업**하고, **마지막 발표 때 모든 산출물을 깔끔하게 제시**할 수 있습니다.

---

**작성자 주**: 이 폴더 구조는 현재 프로젝트의 **실제 진행 경험**(W1~W2 완료, W3 시작)을 바탕으로 설계되었으며, 매주 산출물이 정확히 예상되는 위치에 저장될 때 팀 전체의 신뢰도와 생산성이 **급격히 향상**됩니다.

**Last Updated**: 2026-03-27  
**Status**: 완성 (W8 기준 최적화)
