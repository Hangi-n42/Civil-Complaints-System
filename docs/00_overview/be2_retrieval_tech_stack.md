# BE2 검색(Retrieval) 기술 스택 & 선택 이유

문서 버전: v1.0  
작성 일시: 2026-04-26  
범위: BE2 검색/Adaptive RAG 코어

---

## 1. BE2 검색의 기술 스택 개요

### 1.1 핵심 기술 구성

| 계층 | 기술 | 버전 | 역할 |
|------|------|------|------|
| **벡터 DB** | ChromaDB | 1.5.5 | 벡터 인덱싱 및 의미 검색 |
| **임베딩** | sentence-transformers | (requirements.txt 기반) | 텍스트→벡터 변환 |
| **RAG 프레임워크** | LangChain | 1.0.0 | 검색-생성 파이프라인 연계 |
| **HNSW** | chroma-hnswlib | 0.7.6 | 벡터 유사도 검색 (근사 최근접 이웃) |
| **데이터 검증** | Pydantic | 자동 포함 | 요청/응답 스키마 검증 |
| **백엔드** | FastAPI | 0.115.12 | `/search` API 엔드포인트 |
| **로깅** | Python logging | 표준 | 파이프라인 추적 로그 |

### 1.2 코드 아키텍처 (검색 모듈)

```
app/retrieval/
├── service.py                      # RetrievalService (메인 인터페이스)
├── vectorstores/chroma_store.py    # ChromaVectorStore (DB 어댑터)
├── analyzers/
│   └── complexity_analyzer.py      # 질의 복잡도 분석
├── router/
│   └── adaptive_router.py          # 적응형 라우팅
├── embeddings/                     # 임베딩 모델 관리
└── entity_labels.py                # 엔티티 라벨 정의
```

---

## 2. 각 기술별 선택 이유

### 2.1 ChromaDB (벡터 데이터베이스)

**선택 이유:**
1. **경량성**: 설치/설정 간단, 외부 서버 불필요
2. **로컬 실행**: 온디바이스 운영 원칙 준수 (보안/프라이버시)
3. **빠른 프로토타이핑**: 시간 제약 환경에서 즉시 구성 가능
4. **Persistent 모드**: 로컬 파일시스템에 벡터 인덱스 저장 가능
5. **HNSW 통합**: 고차원 벡터의 효율적 유사도 검색 (cosine 공간)
6. **메타데이터 필터**: 민원 카테고리/지역/엔티티 레이블 필터링 지원

**구현 포인트:**
- `ChromaVectorStore` 클래스가 thin adapter 역할 수행
- Collection name: `civil_cases_v1`
- Distance metric: cosine (의미 유사도)
- Persistent directory: `CHROMA_DB_PATH` 환경 변수로 구성

```python
# 사용 예시
vectorstore = ChromaVectorStore(
    persist_directory="/path/to/chroma_db",
    embedding_model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    embedding_device="cpu"  # or "cuda"
)
```

---

### 2.2 sentence-transformers (임베딩 모델)

**선택 이유:**
1. **다국어 지원**: 한국어 포함 50+ 언어 동시 지원
2. **성능 vs 속도 균형**: 
   - 기본 모델(MiniLM): 영어 기준 41.6M 파라미터 → 빠른 추론
   - 고성능 모델(다국어 L12): 384차원 임베딩
3. **미세조정 용이**: 민원 도메인에 맞춰 fine-tuning 가능
4. **오픈소스**: Hugging Face Hub 통합, 라이선스 자유
5. **배포 간편성**: 단일 forward pass로 텍스트 배치 처리 가능

**모델 선택 기준:**
- 기본값: `paraphrase-multilingual-MiniLM-L12-v2` (다국어, 경량)
- 대안: `sentence-transformers/multilingual-e5-large` (성능 우선)
- 설정: `configs/base.yaml`에서 `EMBEDDING_MODEL` 지정 가능

---

### 2.3 LangChain (RAG 프레임워크)

**선택 이유:**
1. **표준화된 파이프라인**: Retriever → Chain → Output Parser 통일
2. **ChromaDB 통합**: `langchain-chroma` 패키지로 직접 연결
3. **Prompt 템플릿화**: topic별 프롬프트 동적 구성 용이
4. **벡터 스토어 추상화**: 향후 다른 DB로 교체 시 코드 변경 최소화

**BE2에서 LangChain 사용 패턴:**
- `RetrievalService`는 LangChain의 높은 수준 추상화 활용
- 검색 결과를 RAG 컨텍스트로 구성
- `/qa` 엔드포인트로 생성 모듈(Generation)에 전달

---

### 2.4 적응형 RAG 아키텍처 (Adaptive RAG)

BE2의 핵심 혁신은 **질의의 특성에 따라 검색 전략을 동적으로 선택**하는 구조입니다.

#### 2.4.1 ComplexityAnalyzer (질의 분석)

```python
# 민원 질의를 5가지 차원으로 분석
class ComplexityAnalysis:
    complexity_score: float          # 0.0 ~ 1.0
    complexity_level: Literal["low", "medium", "high"]
    intent_count: int               # 의도 개수
    constraint_count: int           # 제약조건 개수
    entity_diversity: int           # 엔티티 유형 수
    policy_reference_count: int     # 법령 참조 수
```

**분석 항목:**
1. **문장 길이**: 단문(short) vs 장문(long)
2. **의도 분해**: "및", "그리고", "또는" 등으로 분리되는 복수 의도
3. **제약조건 탐지**: "기한", "예산", "규정", "절차", "우선순위" 등 키워드
4. **엔티티 다양성**: "기관", "부서", "주민", "시설" 등 개체 유형 수
5. **정책 참조**: "법", "시행령", "조례" 등 법령 언급 여부

**선택 이유:**
- 민원 특성상 간단한 문의도 있고, 다층적 요구를 담은 복합 민원도 있음
- 복잡도에 따라 검색 범위(top-k)와 컨텍스트 크기를 조절하는 것이 효율적
- 기존 고정 임계값 대신 동적 적응 필요

#### 2.4.2 AdaptiveRouter (전략 선택)

```python
# 질의 특성 → 검색 매개변수 매핑
ROUTING_PARAMS_BY_COMPLEXITY = {
    "low":    AppliedParams(top_k=4,  snippet_max_chars=400,  chunk_policy="compact"),
    "medium": AppliedParams(top_k=6,  snippet_max_chars=700,  chunk_policy="balanced"),
    "high":   AppliedParams(top_k=9,  snippet_max_chars=1100, chunk_policy="expanded"),
}
```

**라우팅 결정:**
- **Route key**: `{topic_type}/{complexity_level}` (예: `welfare/high`)
- **Strategy ID**: `topic_{category}_{level}_v1` (예: `topic_welfare_high_v1`)
- **적용 매개변수**:
  - `top_k`: 반환할 상위 유사 사례 개수
  - `snippet_max_chars`: 인용 텍스트 최대 길이
  - `chunk_policy`: 컨텍스트 청킹 전략

---

### 2.5 HNSW (Hierarchical Navigable Small World)

**선택 이유:**
1. **고속 근사 검색**: 정확한 계산이 아닌 근사 최근접 이웃으로 속도 확보
2. **메모리 효율**: O(log n) 검색 성능을 O(n log n) 공간 복잡도로 달성
3. **ChromaDB 기본 엔진**: 별도 설정 없이 자동 사용 가능
4. **Cosine 거리 지원**: 벡터 정규화로 방향 기반 유사도 계산

**성능 특성:**
- 고차원 벡터(384D): 밀리초 단위 검색
- 대규모 데이터셋(10K+ 사례): 선형 시간 복잡도 회피

---

## 3. BE2 검색 파이프라인 (요청-응답)

```
입력 질의 (complaint_id + query + filters)
    ↓
[1] ComplexityAnalyzer.analyze()
    → complexity_score, intent_count, constraint_count, ...
    ↓
[2] AdaptiveRouter.route()
    → strategy_id, route_key, applied_params (top_k, snippet_max_chars, chunk_policy)
    ↓
[3] ChromaVectorStore.query()
    (sentence-transformers로 query를 벡터화)
    (HNSW로 유사 벡터 검색)
    → retrieved_docs[] with similarity_score
    ↓
[4] 필터링 & 스니펫 추출 (route_key 기반)
    → snippet_max_chars 크기로 텍스트 잘라내기
    ↓
출력: routing_trace + routing_hint + retrieved_docs
```

---

## 4. 설정 & 환경

### 4.1 주요 환경 변수

```yaml
# configs/base.yaml
EMBEDDING_MODEL: "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DEVICE: "cpu"  # or "cuda"
CHROMA_DB_PATH: "data/chroma_db/"
```

### 4.2 의존성

```
chromadb==1.5.5
chroma-hnswlib==0.7.6
sentence-transformers  # Hugging Face Hub에서 자동 다운로드
langchain==1.0.0
langchain-chroma==1.1.0
pydantic  # 자동 포함
```

---

## 5. BE2 검색의 강점 & 한계

### 5.1 강점
1. **온디바이스 실행**: 외부 API 의존 없음 → 보안/프라이버시 보장
2. **적응형 라우팅**: 민원 특성에 맞춤형 검색 (저복잡도는 빠르게, 고복잡도는 확장)
3. **메타데이터 필터**: 카테고리/지역 필터로 검색 정확도 향상
4. **투명한 의사결정**: routing_trace로 "왜 이 결과를 선택했는가" 명확
5. **빠른 개발 사이클**: 프로토타이핑 및 실험에 최적

### 5.2 한계 & 개선 방향
1. **단일 언어 최적화 부족**: 다국어 모델 사용하지만 한국어 특화 필요
2. **임베딩 모델 고정**: fine-tuning 미실행 상태 (학습 데이터 수집 필요)
3. **벡터 DB 확장성**: 수백만 건 데이터 규모 시 다른 DB 검토 필요 (Weaviate, Milvus)
4. **성능 프로파일링 부족**: 응답 시간, 메모리 사용량 모니터링 필요
5. **캐싱 미구현**: 반복 질의에 대한 속도 최적화 없음

---

## 6. BE2 검색 채택 의사결정 기록

### 6.1 기술 선택 회고

| 결정 | 선택지 | 채택 기술 | 이유 |
|------|--------|----------|------|
| **벡터 DB** | PostgreSQL+pgvector, Weaviate, Milvus, ChromaDB | ChromaDB | 로컬/경량/빠른 구성 |
| **임베딩** | OpenAI API, Ollama, sentence-transformers | sentence-transformers | 온디바이스, 다국어, 오픈소스 |
| **RAG 프레임워크** | 직접 구현, LangChain, LlamaIndex | LangChain | 표준화, ChromaDB 통합 용이 |
| **검색 전략** | 고정 top_k, 동적 라우팅 | 적응형 RAG | 민원 복잡도 반영 |

### 6.2 주요 마일스톤
- **Week 1-2**: 기본 검색 구현 (정적 top_k)
- **Week 3-4**: 메타데이터 필터 추가
- **Week 5-6**: 적응형 라우팅 통합
- **Week 7+**: 임베딩 모델 fine-tuning 및 성능 최적화 (계획)

---

## 7. 참고 문서

- 기술 스택 가이드: [dev_stack.md](dev_stack.md)
- API 인터페이스: [docs/60_specs/api_interface_spec.md](../60_specs/api_interface_spec.md)
- 데이터 스키마: [docs/60_specs/data_schema_spec.md](../60_specs/data_schema_spec.md)
- Week5-6 액션 플랜: [docs/50_issues/week5_6_adaptive_rag_core_action_plan.md](../50_issues/week5_6_adaptive_rag_core_action_plan.md)
