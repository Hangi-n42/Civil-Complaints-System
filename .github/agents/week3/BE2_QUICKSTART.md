# Week 3 BE2 프롬프트 설계 가이드

**대상**: Issue #92, #101, #102, #103 해결을 위한 BE2(민건)  
**사용 방법**: 아래 3개 문서를 순서대로 참조

---

## 📚 프롬프트 구성 (3개 지층)

### 1️⃣ 첫 번째: 역할 프롬프트 (`.github/agents/week3/be2_retrieval.prompt.md`)

**용도**: BE2 에이전트의 역할, 책임, 위험 관리, 협업 규칙을 **전체적으로 이해**

**주요 내용**:
- 역할 정의 (임베딩/인덱싱/검색/필터 담당)
- 이슈 #101, #102, #103의 고수준 설명
- 협업 인터페이스 (BE1, BE3, FE)
- 리스크 관리 템플릿 (3가지 핵심 위험)
- 성능 폴백 우선순위

**언제 읽을까?**
- ✅ Week 3 시작 전 (미션/책임 파악)
- ✅ 주간 회의 전 (협업 방향 공유)
- ✅ 크리티컬 결정 필요 시 (폴백 전략 검토)

**핵심 문구 (암기)**:
> "BE2는 retrieval 오너로서 민원 구조화 데이터를 벡터 시스템으로 전환하고, 검색 품질을 수치로 개선하는 책임을 진다."

---

### 2️⃣ 두 번째: 상세 명세서 (`.github/agents/week3/be2_issue92_103_specification.md`)

**용도**: 각 이슈(#101, #102, #103)에 대해 **구체적인 액션 아이템, 코드, 산출물을 단계별로 제시**

**포함 내용**:
- **Issue #101**: 500건 인덱싱 (6개 타스크, 각 1~3시간)
  - 101-1: 평가셋 준비
  - 101-2: 메타데이터 정규화 규칙 수립
  - 101-3: 임베딩 배치 파이프라인
  - 101-4: ChromaDB 컬렉션 설정
  - 101-5: 인덱싱 실행
  - 101-6: 리포트 생성

- **Issue #102**: 메타필터 안정화 (6개 타스크)
  - 102-1: 5가지 테스트 시나리오 정의
  - 102-2~5: 각 시나리오 검증
  - 102-6: 필터 검증 리포트

- **Issue #103**: retrieval 지표 측정 (5개 타스크)
  - 103-1: Recall@K 측정
  - 103-2: Latency 측정
  - 103-3: 필터별 성능 분석
  - 103-4: candidate_ax4_light 벤치마크
  - 103-5: 분석 리포트 작성

**언제 읽을까?**
- ✅ **매 타스크 시작 전** (구체적 실행 코드/예시)
- ✅ 코드 작성 중 (템플릿, 함수 시그니처 참고)
- ✅ 산출물 검증 (expected JSON 형식 확인)

**이 문서의 강점**:
- 실행 가능한 Python 코드 스니펫 제공
- JSON 산출물 기대값 명시
- 각 타스크별 "완료 신호" 체크리스트
- 1~3시간 단위 작업 단위로 분해

---

### 3️⃣ 세 번째: 본 가이드 문서 (현재 파일)

**용도**: 세 프롬프트의 **관계 이해** 및 **실행 순서** 정리

**사용 시기**: 이번 설계 구조를 다시 한 번 정리하고 싶을 때

---

## 🎯 실행 흐름

### Phase 1: 준비

```
1. 첫 번째 프롬프트 읽기 (be2_retrieval.prompt.md)
   → "BE2의 책임과 목표가 무엇인가?" 이해
   
2. 두 번째 프롬프트 읽기 (be2_issue92_103_specification.md)
   → "각 이슈별로 뭘 해야 하나?" 파악
   
3. BE1과 협력: 피롤트셋 준비 (Issue #101-1)
   → evaluation_set.json 생성/검증
```

### Phase 2: 구현

#### 메타데이터 정규화 (Issue #101-2)
- REGION_MAPPING, CATEGORY_ENUM 정의
- `app/retrieval/normalization.py` 작성
- 완료 기준: 평가셋 100% 커버리지

#### 임베딩 파이프라인 (Issue #101-3)
- `scripts/build_index.py` 구현
- BGE-m3 테스트 (10건)
- 완료 기준: 임베딩 생성 확인, batch_size 최적화

#### 500건 인덱싱 + 필터 테스트 (Issue #101-5 + #102-1~3)
- 5개 필터 시나리오 정의 및 구현
- 500건 인덱싱 실행 (~ 30분)
- Scenario A~C 검증
- 완료 기준: indexed_count >= 495, filter accuracy 100%

#### 복합 필터 + latency 측정 (Issue #102-4 + #103-1~2)
- Scenario D, E 검증
- Recall@K, latency 측정
- 완료 기준: recall_5 >= 0.75, avg_latency <= 12s

#### 모델 벤치마크 + 분석 (Issue #103-4~5)
- candidate_ax4_light 벤치마크 실행
- 최종 리포트 작성
- 완료 기준: 4개 산출물 모두 생성

### Phase 3: 검토

```
BE1/BE3/FE와 최종 협력 리뷰
→ 각 이슈 코멘트로 근거 산출물 첨부
→ Issue close
```

---

## 📊 산출물 맵핑 (어디에 뭘 넣을까?)

| 이슈 | 산출물 | 경로 | 책임 |
|------|--------|------|------|
| #101 | 인덱싱 리포트 | `logs/evaluation/week3/indexing_report.json` | BE2 |
| #102 | 필터 검증 리포트 | `logs/evaluation/week3/filter_validation.json` | BE2 |
| #103 | retrieval 지표 | `logs/evaluation/week3/retrieval_metrics.json` | BE2 |
| #103 | 모델 벤치마크 | `logs/evaluation/week3/model_benchmark_candidate_ax4_light.json` | BE2 |
| 부가 | 분석 리포트 | `docs/40_delivery/week3/be2_week3_analysis_report.md` | BE2 |

---

## ⚡ 빠른 참조 (업무 중간에 찾고 싶을 때)

### "지금 뭘 해야 해?"
→ 두 번째 프롬프트(`be2_issue92_103_specification.md`)의 **"작업 분해"** 테이블 참고
→ 현재 진행 중인 타스크의 **"실행 코드"** 섹션 확인

### "이게 실패하면 어떻게 해?"
→ 첫 번째 프롬프트(`be2_retrieval.prompt.md`)의 **"리스크 관리"** 섹션 참고
→ 폴백안(Fallback Plan) 3가지 선택지 확인

### "결과물이 정확한지 어떻게 알아?"
→ 두 번째 프롬프트의 각 타스크별 **"완료 신호"** 체크리스트 확인
→ 산출물 JSON의 **"기대값"** 예시와 비교

### "BE1/BE3와 어떻게 협력하지?"
→ 첫 번째 프롬프트의 **"협업 인터페이스"** 섹션(섹션 4)

---

## 🔑 핵심 KPI (최종 성공 기준)

| KPI | 목표 | 측정 방법 |
|-----|------|----------|
| **인덱싱 성공률** | >= 99% (495/500) | indexing_report.json.indexed_count |
| **필터 정확도** | 100% (Scenario A~E all pass) | filter_validation.json.overall_passed |
| **Recall@5** | >= 0.75 | retrieval_metrics.json.recall_5 |
| **Latency (avg)** | <= 12초 | retrieval_metrics.json.avg_latency_ms <= 12000 |
| **모델 안정성** | json_parse >= 0.9 | model_benchmark_*.json.json_parse_success_rate |

**완료 신호**: 위 5개 KPI 전부 달성 시 이슈 #92~#103 complete

---

## 🚨 주의사항

### ⚠️ 자주하는 실수

1. **"평가셋이 없으면?"**
   - → BE1에 즉시 알리고, 예제 샘플로 임시 진행 (최대 100건)
   - → 최종 평가는 500건 완성 후에만 진행

2. **"인덱싱 중 메모리 부족이면?"**
   - → batch_size를 64 → 32로 즉시 축소
   - → 로그에 "OOM detected" 기록
   - → 가능하면 재시도 (자동으로 batch_size 조정)

3. **"필터 결과가 기대와 다르면?"**
   - → 먼저 ChromaDB에 저장된 메타데이터 확인 (region 정규화 여부)
   - → 정규화 규칙 업데이트
   - → Scenario A (필터 없음) 부터 재확인 후 단계별 진행

4. **"latency가 12초를 넘으면?"**
   - → top_k를 5 → 3으로 축소하고 재측정
   - → 필터 조합 효과 분석 (필터 개수 ↑ = latency ↑)
   - → 최악의 경우, baseline 12.5초로 수용 후 명시

---

## 📞 협업 연락처

| 역할 | 담당자 | 관련 이슈 |
|------|--------|----------|
| BE1 (구조화/평가셋) | 이택 | #101-1, #102 (필터값 검증) |
| BE3 (생성/API) | 미정 | #103-5 (citation 신뢰도 정의) |
| FE (UI) | 미정 | #102-6 (필터 UI 동기화) |

**협업 방식**:
- GitHub Issue 코멘트로 질문/답변
- 매일 저녁 6시 팀 회의 (Discord)
- 예상 구현 시간 변경 시 즉시 공유

---

## 📝 마지막 체크리스트

이 가이드를 읽은 후:

- [ ] 첫 번째 프롬프트: BE2의 책임 이해 완료
- [ ] 두 번째 프롬프트: 각 이슈별 할일 메모 작성
- [ ] 산출물 경로: 6개 파일 위치 눈에 익음
- [ ] 성공 기준: 5개 KPI 명확
- [ ] 위험 관리: 3가지 위험-대응책 암기
- [ ] 협업 규칙: BE1/BE3/FE 역할 구분 이해

**준비 완료!** 이제 두 번째 프롬프트를 읽고 구현을 시작하세요.

---

## 🎓 추가 학습 자료

더 깊이 있는 이해를 위해:

1. **Week 3 인터페이스 계약**: `docs/10_contracts/interfaces/week3/week3_be2_interface.md`
2. **BE2 매뉴얼**: `docs/30_manuals/be2_manual.md`
3. **메타필터 스키마**: `docs/20_domains/retrieval/metadata_schema.md`
4. **모델 벤치마크 프로토콜**: `docs/40_delivery/week3/model_benchmark_protocol.md`
5. **PRD (전체 맥락)**: `docs/00_overview/prd.md`

