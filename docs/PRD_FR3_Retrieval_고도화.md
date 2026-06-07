# PRD: FR-3 Retrieval 모듈 고도화
**문서 버전:** v1.0  
**작성일:** 2026-06-02  
**작성자:** (Senior TPM)  
**상태:** 초안(Draft) — 검토 요청  
**관련 모듈:** FR-1 Analyzer, FR-2 Router, FR-3 Retrieval  

---

## 목차

1. [배경 및 현황 분석](#1-배경-및-현황-분석)
2. [문제 정의](#2-문제-정의)
3. [목표 및 성공 지표 (KPI)](#3-목표-및-성공-지표-kpi)
4. [사용자 스토리](#4-사용자-스토리)
5. [기능 요구사항](#5-기능-요구사항)
6. [비기능 요구사항](#6-비기능-요구사항)
7. [시스템 아키텍처 변경 사항](#7-시스템-아키텍처-변경-사항)
8. [인터페이스 명세](#8-인터페이스-명세)
9. [예외 처리 및 엣지 케이스](#9-예외-처리-및-엣지-케이스)
10. [마이그레이션 계획](#10-마이그레이션-계획)
11. [의존성 및 리스크](#11-의존성-및-리스크)
12. [출시 범위 및 단계 계획 (Phasing)](#12-출시-범위-및-단계-계획-phasing)

---

## 1. 배경 및 현황 분석

### 1.1 현재 시스템 구조

현재 FR-3 Retrieval 모듈은 다음 컴포넌트로 구성되어 있다.

| 컴포넌트 | 구현체 | 역할 |
|---|---|---|
| Dense Retriever | ChromaDB + KR-SBERT 임베딩 | 의미 기반 유사도 검색 |
| Sparse Retriever | BM25s (whitespace/korean tokenizer) | 키워드 정확 매칭 |
| Fusion | RRF (Reciprocal Rank Fusion, k=60) | 두 결과 병합 |
| Reranker | CrossEncoder (BAAI/bge-reranker-v2-m3) | 최종 순위 재조정 |
| Routing | AdaptiveRouter | complexity_level(low/medium/high)별 top_k 조정 |

**현재 파라미터 (AdaptiveRouter 기준):**

```
low:    top_k=4,  snippet_max_chars=400,  chunk_policy=compact
medium: top_k=6,  snippet_max_chars=700,  chunk_policy=balanced
high:   top_k=9,  snippet_max_chars=1100, chunk_policy=expanded
```

**검색 정책 (retrieval_policy):**

```
welfare:      admin_policy
traffic:      field_ops
environment:  field_ops
construction: field_ops
general:      general
```

### 1.2 데이터 기반 현황 진단

평가 데이터셋(eval_set_v1) 분석 결과 다음 병목이 식별되었다.

| 문제 구분 | 측정값 | 기준 |
|---|---|---|
| multi-hop 질의(복합 민원) Recall@5 | 0.51 | 목표 0.75 이상 |
| 고유명사/법령 조항 번호 포함 질의 실패율 | 23% | 목표 5% 이하 |
| complexity=high 질의 평균 응답 지연 | 1,820ms | 목표 800ms 이하 |
| 동의어 변형 질의(예: "주정차 단속" vs "불법 주차 단속") Hit@1 | 0.44 | 목표 0.70 이상 |
| ChromaDB 콜드스타트 재인덱싱 소요 시간 | 약 40분 | 목표 10분 이하 |

### 1.3 근본 원인 분석

**[원인 A] Embedding 기반 검색의 Semantic Collapse 문제**  
"도로교통법 시행령 제19조 제2항"과 같은 정확한 법령 조항 번호, 사업자 등록번호, 시설물 관리 코드 등 symbolic token은 임베딩 공간에서 의미적으로 유사한 다른 조항과 합쳐지는 semantic collapse가 발생한다. 이는 민원 처리의 정확성에 직결되는 치명적 결함이다.

**[원인 B] Multi-hop 질의에 대한 단일 검색의 한계**  
"A 도로 공사로 인해 B 버스 노선이 우회 운행 중인데, C 정류장 이용 불편 민원 처리 절차는?"과 같은 복합 민원은 단일 벡터 쿼리로 세 개의 독립적 사실(공사 정보, 노선 변경, 절차)을 동시에 검색할 수 없다.

**[원인 C] BM25 인덱스의 동적 갱신 불가**  
현재 BM25 인덱스는 ChromaDB에서 전체 문서를 읽어 정적으로 빌드한다. 신규 민원 케이스 추가 시 전체 재인덱싱이 필요하며, 이 과정에서 서비스 응답 품질이 저하된다.

---

## 2. 문제 정의

### Problem Statement

> 현재 FR-3 Retrieval 모듈은 단일 벡터 쿼리 기반의 정적 파이프라인으로 설계되어, (1) 법령 조항·행정 코드 등 lexical precision이 요구되는 민원에서 정확도가 낮고, (2) 복합 의도를 가진 multi-hop 민원에서 단일 검색으로 필요한 모든 근거를 수집하지 못하며, (3) 인덱스 갱신 비용이 높아 운영 확장성이 부족하다.

### 해결 방향

- **Lexical Gap 해소:** Unix shell 기반 Direct Corpus Interaction(DCI) 엔진을 도입하여 exact matching이 필요한 질의에서 법령 조항·코드를 정밀 검색한다.
- **Multi-hop 지원:** complexity=high 질의에 대해 GrepSeek 방식의 iterative 검색 에이전트를 적용, 단계적으로 브릿지 엔티티를 수집한다.
- **하이브리드 라우팅:** complexity 레벨에 따라 기존 Hybrid(Dense+BM25) 경로와 DCI 경로를 동적으로 선택한다.

---

## 3. 목표 및 성공 지표 (KPI)

### 3.1 정량적 목표

| 지표 | 현재값 | 목표값 | 측정 방법 |
|---|---|---|---|
| **Multi-hop Recall@5** | 0.51 | **≥ 0.75** | eval_set_v1 multi-hop 서브셋 |
| **법령조항 Hit@1** | 0.44 | **≥ 0.72** | 법령 키워드 포함 질의 서브셋 |
| **complexity=high P95 지연** | 1,820ms | **≤ 800ms** | APM 측정 |
| **complexity=low/medium P95 지연** | 320ms | **≤ 200ms** | APM 측정 (현행 유지/개선) |
| **DCI 검색 실패율** (zero-result) | — | **≤ 8%** | DCI 경로 질의 중 결과 없음 비율 |
| **BM25 재인덱싱 시간** | 40분 | **≤ 10분** | 운영 측정 |
| **전체 MRR@10** | 0.62 | **≥ 0.78** | 전체 eval_set_v1 |

### 3.2 정성적 목표

- 엔지니어가 검색 전략을 `configs/routing.yaml` 한 파일에서 관리할 수 있는 구성 가능성(Configurability) 확보
- 각 검색 단계의 latency 및 결과를 `retrieval_trace`로 완전히 로깅하여 디버깅 가능성 보장
- 기존 `RetrievalService` 인터페이스를 변경하지 않아 FR-4 Generation 모듈의 수정 최소화

---

## 4. 사용자 스토리

### 4.1 최종 사용자 (민원 처리 공무원)

```
As 민원 처리 공무원,
I want 복합 민원("도로 공사 + 버스 노선 변경 + 민원 절차")을 한 번에 조회했을 때
       관련 근거 문서 3건 이상을 각각 출처와 함께 받기를 원한다.
So that 민원인에게 법적 근거를 명시한 처리 결과를 신속히 안내할 수 있다.
```

```
As 민원 처리 공무원,
I want "도로교통법 시행령 제19조"를 언급한 민원에서
       해당 조항이 포함된 문서를 반드시 1순위로 받기를 원한다.
So that 법령 오인에 의한 잘못된 민원 처리를 방지할 수 있다.
```

### 4.2 시스템 관리자 / 운영자

```
As 시스템 관리자,
I want 신규 민원 케이스 100건이 추가될 때
       BM25 인덱스를 10분 이내에 증분 업데이트할 수 있기를 원한다.
So that 운영 중 서비스 품질 저하 없이 데이터를 최신 상태로 유지할 수 있다.
```

### 4.3 개발자

```
As 백엔드 개발자,
I want retrieval_trace에서 각 검색 단계(DCI command, BM25 score, dense score, rerank score)를
       JSON으로 확인할 수 있기를 원한다.
So that 검색 품질 이슈 발생 시 어느 단계에서 실패했는지 즉시 진단할 수 있다.
```

---

## 5. 기능 요구사항

### FR3-F01: 라우팅 전략 이원화

**설명:** AdaptiveRouter가 `(topic_type, complexity_level)`을 기반으로 검색 경로를 두 가지 중 하나로 결정한다.

| 조건 | 검색 경로 |
|---|---|
| complexity_level == "high" | **DCI 경로** (GrepSeek Agent) |
| complexity_level in ["low", "medium"] | **Hybrid 경로** (기존 Dense + BM25 + RRF + Rerank) |

**수용 기준:**
- `RoutingDecision` 객체에 `retrieval_path: Literal["dci", "hybrid"]` 필드가 추가된다.
- 라우팅 변경은 `configs/routing.yaml`의 `dci_complexity_threshold` 값으로 조정 가능하다. (기본값: `"high"`)

---

### FR3-F02: DCI Agent (GrepSeek 방식) 구현

**설명:** Unix shell 커맨드(`rg`, `grep`, `awk`, `head`)를 사용해 corpus JSONL 파일을 직접 탐색하는 검색 에이전트를 구현한다. ReAct 프레임워크 기반으로 최대 T=6 턴 내에 질의를 해결한다.

**세부 요구사항:**

**FR3-F02-1: 멀티턴 검색 루프**
- 에이전트는 `<think>` 블록에서 현재 수집된 증거와 미수집 정보를 추론한다.
- 추론 결과를 바탕으로 `rg -F "[키워드]" corpus.jsonl | head -n [N]` 형태의 단일 파이프라인 커맨드를 생성한다.
- 커맨드 실행 결과(`observation`)를 히스토리에 누적하며 다음 커맨드를 결정한다.
- `<answer>` 블록 출력 시 탐색을 종료한다.

**FR3-F02-2: 허용 커맨드 화이트리스트**
```
허용: rg, grep, head, tail, awk, sed, cut, sort, uniq, wc, tr
금지: 리디렉션(> <), 커맨드 체이닝(; && ||), 커맨드 치환($(...))
```

**FR3-F02-3: 안전 제한**
- 단일 커맨드 출력 최대: `head -n 8` (초과 시 자동 truncation)
- 최대 턴 수: T=6 (초과 시 현재까지 수집된 결과로 강제 종료)
- 커맨드 타임아웃: 3초/커맨드

**FR3-F02-4: Sharded-Parallel Execution**
- corpus를 S개 shard로 분할하여 병렬 실행한다. (기본 S=8)
- 파이프라인 유형별 merge 전략:
  - CONCAT: 순수 stateless 파이프라인 (rg | grep)
  - HEAD: `head -n K`로 끝나는 파이프라인
  - COUNT: `wc -l`로 끝나는 파이프라인
  - SEQUENTIAL: cross-line context가 필요한 파이프라인 (fallback)

**FR3-F02-5: DCI 출력 스키마**
```python
@dataclass
class DCIResult:
    passages: List[str]              # 수집된 증거 텍스트
    trajectory: List[DCIStep]        # [(think, command, observation), ...]
    bridge_entities: List[str]       # 멀티홉 브릿지 엔티티
    turn_count: int                  # 실행된 턴 수
    latency_ms: float
```

---

### FR3-F03: Hybrid 경로 개선 (기존 경로 유지 + 증분 BM25)

**설명:** 기존 Dense+BM25+RRF+Rerank 파이프라인을 유지하되, BM25 인덱스 갱신 방식을 개선한다.

**FR3-F03-1: 증분 BM25 인덱스 업데이트**
- 신규 문서 추가 시 전체 재빌드 대신 증분 추가(append) 방식으로 인덱스를 갱신한다.
- 증분 업데이트 실행 시간: 100건 기준 ≤ 2분

**FR3-F03-2: Korean Tokenizer 기본 적용**
- 현재 whitespace tokenizer를 korean tokenizer(kiwipiepy)로 기본 전환한다.
- 기존 인덱스(`civil_cases_v1_whitespace`)와 신규 인덱스(`civil_cases_v1_korean`)를 병행 운영하다가 평가 후 전환한다.

---

### FR3-F04: 통합 Retrieval Trace 로깅

**설명:** 검색 경로(DCI/Hybrid) 무관하게 동일한 형식의 `retrieval_trace`를 반환한다.

```python
# retrieval_trace 스키마
{
    "retrieval_path": "dci" | "hybrid",
    "route_key": "traffic/high",
    "strategy_id": "topic_traffic_high_v2",
    
    # DCI 경로 전용
    "dci_trajectory": [
        {
            "turn": 1,
            "think": "...",
            "command": "rg -F '교통신호' corpus.jsonl | head -n 3",
            "observation": "...",
            "latency_ms": 42.1
        }
    ],
    "dci_bridge_entities": ["도로교통법 제19조", "신호등 관리 지침"],
    
    # Hybrid 경로 전용
    "bm25_top3_scores": [0.92, 0.87, 0.81],
    "dense_top3_scores": [0.88, 0.83, 0.77],
    "rrf_top3_scores": [0.95, 0.91, 0.86],
    "rerank_top3_scores": [0.97, 0.92, 0.84],
    
    # 공통
    "total_latency_ms": 340.5,
    "retrieved_doc_count": 6
}
```

---

### FR3-F05: Corpus 관리 API

**설명:** DCI 엔진이 탐색할 corpus JSONL 파일과 ChromaDB를 동기화하는 관리 기능을 제공한다.

| 엔드포인트 | 메서드 | 설명 |
|---|---|---|
| `/admin/corpus/export` | POST | ChromaDB → corpus.jsonl 내보내기 |
| `/admin/corpus/sharding` | POST | corpus.jsonl을 S개 shard로 분할 |
| `/admin/corpus/status` | GET | corpus 최종 갱신 시각, shard 수, 문서 수 반환 |
| `/admin/index/bm25/rebuild` | POST | BM25 전체 재빌드 (운영 시간 외 사용) |
| `/admin/index/bm25/update` | POST | 증분 업데이트 (신규 문서 ID 목록 전달) |

---

## 6. 비기능 요구사항

### 6.1 성능

| 항목 | 요구 사항 |
|---|---|
| DCI 경로 P95 응답 지연 | ≤ 800ms (sharded execution 포함) |
| Hybrid 경로 P95 응답 지연 | ≤ 200ms |
| DCI corpus scan (S=8 shard) | ≤ 100ms / 커맨드 |
| 동시 처리 | 초당 20 req 이상 무중단 처리 |

### 6.2 안정성

| 항목 | 요구 사항 |
|---|---|
| DCI 커맨드 실행 오류 시 | Hybrid 경로로 자동 폴백, 에러 로깅 |
| ChromaDB 불가 시 | BM25 단독 검색으로 degraded mode 동작 |
| corpus.jsonl 미존재 시 | DCI 비활성화, Hybrid 강제 사용, 알림 발송 |
| 서비스 가용성 | 월 99.5% 이상 |

### 6.3 보안

| 항목 | 요구 사항 |
|---|---|
| Shell Injection 방지 | 커맨드 파라미터는 whitelist 검증 후 실행 |
| corpus 파일 접근 | 읽기 전용 마운트, 쓰기 불허 |
| 관리 API 인증 | Admin 토큰 필수 (기존 auth 미들웨어 활용) |

### 6.4 관측 가능성 (Observability)

| 항목 | 요구 사항 |
|---|---|
| 메트릭 | Prometheus: `retrieval_latency_ms{path="dci\|hybrid"}`, `dci_turn_count`, `dci_zero_result_total` |
| 로그 | 구조화 JSON 로그, retrieval_trace 전체 포함 |
| 알림 | zero_result_rate > 10% 시 PagerDuty 알림 |

---

## 7. 시스템 아키텍처 변경 사항

### 7.1 현재 아키텍처

```
Query → RetrievalService
          └── HybridRetriever
                ├── BM25RetrieveStage
                ├── ChromaDenseStage
                ├── RRFFusionStage
                └── CrossEncoderRerankStage
```

### 7.2 목표 아키텍처

```
Query → RetrievalService
          └── AdaptiveRouter (path 결정)
                ├── [path=dci]    DCIRetriever
                │                   ├── GrepSeekAgent
                │                   │     ├── CommandExecutor (sharded)
                │                   │     │     ├── Shard 1..N (parallel)
                │                   │     │     └── MergeEngine
                │                   │     └── ReActLoop (max 6 turns)
                │                   └── DCIResultFormatter
                │
                └── [path=hybrid] HybridRetriever (기존 유지)
                                    ├── BM25RetrieveStage (korean tokenizer)
                                    ├── ChromaDenseStage
                                    ├── RRFFusionStage
                                    └── CrossEncoderRerankStage
```

### 7.3 파일 시스템 구조 변경

```
data/
├── bm25_index/
│   ├── civil_cases_v1_whitespace/   (기존, 유지)
│   └── civil_cases_v1_korean/       (신규)
├── corpus/
│   ├── corpus.jsonl                 (전체 corpus, DCI용)
│   └── shards/
│       ├── shard_01.jsonl
│       ├── shard_02.jsonl
│       └── ...shard_N.jsonl
└── chroma/                          (기존 유지)
```

---

## 8. 인터페이스 명세

### 8.1 RetrievalService 인터페이스 (변경 없음)

기존 `RetrievalService.search()` 시그니처는 변경하지 않는다. 내부 구현만 교체한다.

```python
# 기존 시그니처 유지
async def search(
    self,
    query: str,
    collection_name: str = "civil_cases_v1",
    top_k: int = 6,
    routing_trace: Optional[dict] = None,
) -> List[RetrievedDoc]:
    ...
```

### 8.2 RoutingDecision 확장

```python
@dataclass(frozen=True)
class RoutingDecision:
    route_key: str
    strategy_id: str
    applied_params: AppliedParams
    route_reason: str
    retrieval_policy: RetrievalPolicy
    retrieval_path: Literal["dci", "hybrid"]  # ← 신규 필드
```

### 8.3 RetrievedDoc 확장

```python
@dataclass
class RetrievedDoc:
    qid: str
    docid: str
    score: float
    rank: int
    stage: str
    metadata: dict
    # ← 신규 필드
    source_type: Literal["dci", "hybrid"] = "hybrid"
    dci_command: Optional[str] = None      # 해당 문서를 찾은 shell 커맨드
    dci_turn: Optional[int] = None         # 몇 번째 턴에서 수집되었는지
```

### 8.4 DCIAgent 내부 인터페이스

```python
class DCIAgent:
    async def search(
        self,
        query: str,
        complexity_trace: dict,
        max_turns: int = 6,
    ) -> DCIResult: ...

class ShardedCommandExecutor:
    async def execute(
        self,
        command: str,
        timeout_sec: float = 3.0,
    ) -> CommandResult: ...
    
    def classify_pipeline(self, command: str) -> PipelineType: ...
    # PipelineType: Literal["CONCAT", "HEAD", "COUNT", "SEQUENTIAL"]
```

---

## 9. 예외 처리 및 엣지 케이스

### 9.1 DCI 경로 예외

| 예외 상황 | 감지 방법 | 대응 |
|---|---|---|
| corpus.jsonl 미존재 | 시작 시 파일 존재 확인 | DCI 비활성화 + Hybrid 강제, 관리자 알림 |
| Shell Injection 시도 | 커맨드 whitelist 검증 실패 | 즉시 거부(400), 보안 로그 기록 |
| 커맨드 타임아웃 (>3s) | asyncio.wait_for | 해당 턴 스킵, 다음 턴 계속 |
| 최대 턴 수 초과 (T>6) | turn_count 카운터 | 현재까지 수집된 passages로 강제 종료 |
| 모든 턴 zero-result | observation 비어있음 확인 | Hybrid 폴백 후 `retrieval_trace.fallback=true` 기록 |
| Shard 실행 실패 (일부) | subprocess 오류 코드 | 해당 shard 결과 제외 후 나머지로 병합 |
| 전체 Shard 실패 | 모든 subprocess 오류 | SEQUENTIAL 모드로 재시도 |

### 9.2 Hybrid 경로 예외

| 예외 상황 | 감지 방법 | 대응 |
|---|---|---|
| ChromaDB 연결 실패 | httpx.ConnectError | BM25 단독 결과 반환, degraded mode 로깅 |
| CrossEncoder 모델 로드 실패 | 첫 호출 시 예외 | RRF 결과 그대로 반환 (rerank 생략) |
| BM25 인덱스 없음 | 파일 존재 확인 | Dense 단독 결과 반환, BM25 재빌드 스케줄링 |
| top_k 결과 부족 (n < top_k) | len(results) 확인 | 가용한 결과만 반환, 부족 사유 로깅 |

### 9.3 엣지 케이스

| 케이스 | 처리 방법 |
|---|---|
| 빈 쿼리 (`""`) | 422 Validation Error 즉시 반환 |
| 쿼리 길이 > 500자 | 500자로 truncation 후 처리 (경고 로그) |
| 한글 + 영문 혼합 쿼리 | DCI에서 `-i` (case-insensitive) 플래그 자동 추가 |
| 특수문자 포함 법령 번호 (괄호, 점) | DCI에서 `-F` (fixed string) 플래그로 정규식 이스케이프 없이 처리 |
| corpus shard 수 > CPU 코어 수 | shard 수를 CPU 코어 수로 자동 조정 |
| collection 미존재 | `RetrievalError(code="COLLECTION_NOT_FOUND")` 반환 |

---

## 10. 마이그레이션 계획

### 10.1 단계별 마이그레이션 (Blue-Green 방식)

**Phase 0: 사전 준비 (0주차)**
- corpus.jsonl 내보내기 자동화 스크립트 개발 및 검증
- shard 분할 유틸리티 개발 (S=8 기본)
- 기존 eval_set_v1 기준 Baseline 지표 재측정 및 문서화

**Phase 1: Korean Tokenizer 전환 (1-2주차)**
- `civil_cases_v1_korean` 인덱스 빌드
- A/B 테스트: 전체 트래픽의 20%를 korean tokenizer로 라우팅
- MRR@10, Hit@1 지표 비교 후 100% 전환 결정

**Phase 2: DCI 엔진 내부 검증 (3-4주차)**
- DCI Agent를 production 트래픽과 독립된 staging 환경에서 운영
- eval_set_v1의 complexity=high 서브셋으로 품질 평가
- Recall@5 ≥ 0.75 달성 시 다음 단계 진입

**Phase 3: DCI 경로 Shadow Mode (5주차)**
- complexity=high 질의에서 Hybrid와 DCI를 동시 실행
- 응답은 Hybrid 결과 사용, DCI 결과는 로깅만
- 두 경로의 결과 품질 비교 분석

**Phase 4: DCI 경로 점진적 활성화 (6-8주차)**
- complexity=high 트래픽의 10% → 30% → 50% → 100% 순차 전환
- 각 단계에서 Error Rate < 1%, P95 ≤ 800ms 확인 후 다음 단계

**Phase 5: 안정화 및 구 경로 정리 (9-10주차)**
- 전체 DCI 경로 활성화 후 2주간 모니터링
- whitespace BM25 인덱스 폐기 (disk 회수)

### 10.2 롤백 계획

| 롤백 트리거 | 자동 롤백 기준 | 수동 롤백 절차 |
|---|---|---|
| Error Rate 급증 | DCI error rate > 5% (5분 이내) | `routing.yaml`의 `dci_enabled: false`로 변경 후 배포 |
| P95 지연 초과 | DCI P95 > 1,200ms (10분 지속) | 동일 |
| 품질 하락 | MRR@10 < 0.60 (일간 측정) | 수동 분석 후 결정 |

---

## 11. 의존성 및 리스크

### 11.1 외부 의존성

| 의존성 | 버전 | 용도 | 대안 |
|---|---|---|---|
| ripgrep (rg) | ≥ 14.x | DCI 핵심 검색 도구 | grep (성능 저하) |
| bm25s | ≥ 0.2.x | BM25 인덱스 | 기존 버전 유지 |
| kiwipiepy | ≥ 0.18.x | 한국어 형태소 분석 | whitespace tokenizer |
| asyncio (stdlib) | — | shard 병렬 실행 | — |
| BAAI/bge-reranker-v2-m3 | — | CrossEncoder reranking | bge-reranker-base |

### 11.2 리스크 및 완화 방안

| 리스크 | 발생 확률 | 영향도 | 완화 방안 |
|---|---|---|---|
| DCI 에이전트의 과도한 broad search (corpus 전체 스캔) | 중 | 고 | 커맨드 타임아웃 + head -n 제한 강제 적용 |
| corpus.jsonl과 ChromaDB 데이터 불일치 | 중 | 중 | 일일 자동 동기화 + 버전 체크섬 비교 |
| GrepSeek 학습 모델 도메인 미적합 | 고 | 고 | Phase 2에서 민원 데이터 도메인 평가 후 Cold-start SFT 검토 |
| sharding 중 데이터 손실 | 저 | 고 | line-aligned 분할 + checksum 검증 |
| DCI 경로 추가로 인한 복잡도 증가 | 중 | 중 | 라우팅 로직 단일 파일 집중화, 통합 테스트 커버리지 90% 목표 |

---

## 12. 출시 범위 및 단계 계획 (Phasing)

### MVP (Phase 1-2, 4주)

- [ ] corpus.jsonl 내보내기 및 shard 분할 유틸리티
- [ ] Korean tokenizer BM25 인덱스 전환
- [ ] DCIAgent 기본 구현 (ReAct loop, command whitelist, timeout)
- [ ] ShardedCommandExecutor (CONCAT, HEAD, COUNT, SEQUENTIAL)
- [ ] RoutingDecision.retrieval_path 필드 추가
- [ ] retrieval_trace 통합 로깅 스키마 구현
- [ ] Unit test: DCIAgent, ShardedCommandExecutor, AdaptiveRouter (path)

### v1.0 (Phase 3-4, 8주)

- [ ] Shadow mode 운영 및 품질 비교 리포팅
- [ ] DCI 경로 점진적 트래픽 전환
- [ ] Prometheus 메트릭 / Grafana 대시보드
- [ ] 관리 API (corpus 동기화, BM25 증분 업데이트)
- [ ] 자동 롤백 알림 연동

### v1.1 (Phase 5 이후)

- [ ] DCI Cold-start SFT: 민원 도메인 특화 검색 커맨드 학습 데이터 구축
- [ ] Fuzzy matching 지원 (`--max-count`, `--ignore-case` 확장)
- [ ] 멀티 corpus 지원 (법령 corpus, 민원 corpus 분리 탐색)

---

*본 PRD는 초안이며, 검토 후 확정 버전으로 업데이트됩니다.*  
*변경 이력은 Git commit history로 관리합니다.*
