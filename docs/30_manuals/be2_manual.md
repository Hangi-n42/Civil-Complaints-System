# BE2 매뉴얼(민건)

문서 버전: v1.1  
기준 문서: [PRD](../00_overview/prd.md), [WBS](../00_overview/wbs_8weeks_v2_updated.md), [Week3 공통 인터페이스](../10_contracts/interfaces/week3/week3_common_interface.md), [Week3 BE2 인터페이스](../10_contracts/interfaces/week3/week3_be2_interface.md)  
작성일: 2026-03-11  
최신화: 2026-03-27 (M1 완료, M2 진행중 기준 반영)

## 1. 문서 목적

이 문서는 BE2의 검색 축 책임을 실행 단위로 고정한다.  
핵심은 Week3~Week4에 index-search E2E를 안정화하고, Week4 단일 RAG baseline으로 연결 가능한 retrieval 기준선을 만드는 것이다.

## 2. BE2 한 줄 정의

**BE2는 구조화 데이터를 검색 가능한 지식 인덱스로 전환하고, 검색 품질을 수치로 개선하는 retrieval 오너다.**

## 3. 현재 단계 진단 (2026-03-27)

- M1(W1~W2): 완료
	- 기술 스택 확정(BGE-m3, ChromaDB, 로컬 추론 기반)
- M2(W3~W4): 진행중
	- 우선순위: 인덱싱 500건 완료, 필터 검색 안정화, Recall@K/latency 기준선 확보
	- Week4 진입 게이트: 단일 RAG baseline에 투입 가능한 검색 결과 품질 확보

## 4. BE2 최종 책임 범위

### 주 책임
- 임베딩/인덱싱 파이프라인 구현 및 운영
- 벡터 저장소 스키마와 컬렉션 전략 고정
- 검색 API 품질(정확도, 지연시간, 필터 안정성) 개선
- retrieval 성능 평가 자동화
- 후보 모델 1(`candidate_ax4_light`) 벤치마크 실행 결과 정리

### 협업 책임
- BE1 데이터 스키마를 인덱싱 가능한 형태로 연결
- BE3가 generation/citation 검증에 활용 가능한 검색 trace 제공
- FE가 안정적으로 표시할 수 있는 SearchResult 포맷 유지

### 담당 제외
- 구조화 규칙 보정 주도(소유: BE1)
- JSON 파싱/재시도 및 validation 엔진 주도(소유: BE3)
- 데모 UI 구현 주도(소유: FE)

## 5. 핵심 산출물 (현재~종료)

### 코드/설정
- 검색 서비스: `app/retrieval/service.py`
- 인덱스 빌드 스크립트: `scripts/build_index.py`
- 필터 점검 스크립트: `scripts/check_chromadb_filters.py`
- 모델 벤치마크 설정: `configs/week3_model_benchmark.yaml`

### 데이터/리포트
- 인덱싱 입력 기준: `docs/40_delivery/week3/model_test_assets/evaluation_set.json`
- 검색 평가 리포트: `logs/evaluation/week3/retrieval_metrics.json`
- 모델별 실행 리포트: `logs/evaluation/week3/model_benchmark_*.json`
- 통합 리포트 입력 데이터(검색 관련 파트)

## 6. 마일스톤별 실행 계획

## M2 (W3~W4, 현재 진행중)

### 목표
- index-search E2E 완성 + Gate A 검색 기준선 확보

### BE2 실행 항목
- [ ] 500건 인덱싱 성공률 100% 확인
- [ ] 지역/카테고리/기간 필터 2종 이상 안정화
- [ ] Top-K 검색 결과 포맷 Week3 계약과 일치 확인
- [ ] `scripts/evaluate_retrieval.py`로 Recall@5 산출
- [ ] 후보 1(`candidate_ax4_light`) 벤치마크 실행 및 결과 제출

### 완료 기준
- [ ] 검색 요청 실패율 허용 범위 내 유지
- [ ] Recall@5 초기값 산출 및 개선 계획 제시
- [ ] FE/BE3 연동에서 필드 불일치 이슈 0건

## M3 (W5~W6)

### 목표
- Adaptive RAG 구간 대비 retrieval 전략 분기 준비

### BE2 실행 항목
- 길이/주제 기반 retrieval 파라미터 분기 실험
- top_k/chunk/filter 조합별 성능 비교
- 하이브리드 검색 적용 여부 결정(조건부)

### 완료 기준
- baseline 대비 분기 전략의 개선/악화 근거 확보
- retrieval 설정이 config 중심으로 관리됨

## M4 (W7~W8)

### 목표
- 검색 안정화와 데모 품질 고정

### BE2 실행 항목
- 검색 지연시간 병목 정리 및 최종 튜닝
- 데모 시나리오 3종 검색 품질 회귀 테스트
- 발표용 retrieval 아키텍처/지표 자료 제공

### 완료 기준
- 검색 결과가 시연 중 반복 실행에서도 일관됨
- 최종 성능 리포트가 발표 자료와 연결됨

## 7. 입출력 계약 (핸드오프 명세)

### BE2가 받아야 할 것
- BE1: 구조화 데이터 + 필수 메타키(`region`, `category`, `created_at`)
- FE: 화면에 필요한 결과 필드와 정렬/필터 요구사항
- BE3: generation 입력으로 필요한 검색 trace 형식

### BE2가 넘겨줘야 할 것
- SearchResult 표준 포맷(순위, score, content, metadata)
- retrieval 평가 결과(Recall@K, latency)
- 모델 후보 1 벤치마크 결과 파일
- 인덱스 운영 규칙(컬렉션/경로/버전)

## 8. 주간 운영 체크리스트

- [ ] 인덱싱 실패 케이스를 별도 로그로 분리했는가?
- [ ] 필터 조합 테스트(무필터/단일/복합)가 모두 통과하는가?
- [ ] 검색 지연시간 평균/95p를 수집했는가?
- [ ] retrieval 출력이 generation 입력 요구와 일치하는가?
- [ ] 평가셋 고정 버전으로 반복 측정하고 있는가?

## 9. BE2 핵심 리스크 관리

### 리스크 1: 검색 품질 저하 상태로 generation 단계 진행
- 징후: 답변 오류가 반복되고 citation 정합성도 함께 하락
- 원인: retrieval 품질 미검증 상태에서 QA만 조정
- 예방책: 주간 Recall@K 측정 고정
- 대응책: chunk/top_k/filter 전략 재튜닝
- 최악의 경우 폴백안: 고성능 조합 파라미터를 데모 기본값으로 고정

### 리스크 2: 필터 불일치로 UI/백엔드 동작 불안정
- 징후: 같은 질의에서 조건별 결과가 예측 불가
- 원인: 메타키 스키마 불일치, 값 표준화 누락
- 예방책: 인덱싱 전 메타데이터 normalize
- 대응책: 필터 검증 스크립트와 회귀 테스트 실행
- 최악의 경우 폴백안: 데모에서는 검증 완료된 필터 subset만 활성화

### 리스크 3: 벡터 저장소 전략 변경이 후반까지 반복
- 징후: ChromaDB/FAISS 재논의로 구현 지연
- 원인: 기준 없는 성능 비교
- 예방책: M2에서는 ChromaDB 고정, 교체 실험은 별도 트랙
- 대응책: 병목 구간 수치화 후 필요 시 조건부 실험
- 최악의 경우 폴백안: ChromaDB 기준으로 최종 동결

## 10. 최종 완료 기준

- 구조화 데이터를 안정적으로 임베딩/인덱싱할 수 있다.
- Top-K 검색과 메타필터가 데모 조건에서 일관되게 동작한다.
- 검색 품질 개선 결과를 수치로 재현할 수 있다.
- FE/BE3가 즉시 연동 가능한 안정된 검색 계약을 제공한다.
