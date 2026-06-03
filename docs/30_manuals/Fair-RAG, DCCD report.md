# 두 논문의 방법론 비교·분석 보고서

## 대상 논문

1. **FAIR-RAG: Faithful Adaptive Iterative Refinement for Retrieval-Augmented Generation**  
   - 주제: 복잡한 질의에 대한 반복적 검색 증강 생성(RAG) 프레임워크
   - 핵심 방법: Structured Evidence Assessment(SEA)를 중심으로 한 증거 기반 반복 검색·개선

2. **Draft-Conditioned Constrained Decoding for Structured Generation in LLMs**  
   - 주제: 구조화 출력 생성을 위한 constrained decoding 개선
   - 핵심 방법: Draft-Conditioned Constrained Decoding(DCCD)을 통한 의미 계획과 구조 제약의 분리

---

# 1. FAIR-RAG 방법론 상세 정리

## 1.1 방법론의 핵심 아이디어

**FAIR-RAG(Faithful Adaptive Iterative Refinement for RAG)**는 기존 Retrieval-Augmented Generation(RAG)의 한계를 보완하기 위해 제안된 **agentic iterative RAG 프레임워크**이다.

기존 RAG는 일반적으로 다음과 같은 단순 흐름을 따른다.

```text
사용자 질의 → 문서 검색 → 검색 문서 기반 답변 생성
```

그러나 multi-hop question answering처럼 여러 문서와 여러 추론 단계를 거쳐야 하는 질의에서는 단일 검색만으로 충분한 증거를 확보하기 어렵다. FAIR-RAG는 이를 해결하기 위해 다음 원리를 사용한다.

> 현재까지 확보한 증거가 질의의 요구사항을 얼마나 충족하는지 구조적으로 평가하고, 부족한 정보만 다시 검색한다.

즉, FAIR-RAG는 단순히 검색을 반복하는 것이 아니라, **증거의 충분성(sufficiency)**을 평가하고, 남은 정보 공백(gap)을 다음 검색 질의로 변환하는 방식이다.

---

## 1.2 전체 파이프라인

FAIR-RAG의 전체 흐름은 다음과 같이 정리할 수 있다.

```text
[1] 사용자 질의 입력
        ↓
[2] Adaptive Routing
        ↓
[3] Query Decomposition 또는 Query Refinement
        ↓
[4] Retrieval
        ↓
[5] Evidence Filtering
        ↓
[6] Structured Evidence Assessment(SEA)
        ↓
[7] 증거가 충분하면 최종 답변 생성
        ↓
[8] 부족하면 refined query 생성 후 반복
```

핵심은 **SEA → Query Refinement → Retrieval**로 이어지는 반복 루프이다.

---

## 1.3 Step 1: Initial Query Analysis and Adaptive Routing

FAIR-RAG는 먼저 사용자 질의 `x`를 분석하여 질의의 난이도와 필요한 처리 경로를 결정한다.

질의 유형은 대략 다음과 같이 분류된다.

| 유형 | 설명 | 처리 방식 |
|---|---|---|
| **OBVIOUS** | 외부 검색 없이도 답할 수 있는 단순·상식 질의 | LLM 내부 지식으로 바로 답변 |
| **SMALL** | 단순 검색으로 해결 가능한 사실형 질의 | 가벼운 RAG 수행 |
| **LARGE** | 여러 문서의 종합이 필요한 질의 | 반복 검색 수행 |
| **REASONING** | multi-hop reasoning, 비교, 분석이 필요한 질의 | 복잡한 반복 refinement 수행 |

이 단계의 목적은 모든 질의에 동일한 계산량을 쓰지 않고, 질의 난이도에 따라 적절한 resource allocation을 수행하는 것이다.

다만 실험 비교에서는 공정성을 위해 일부 shortcut 또는 고급 retrieval 설정을 비활성화한 것으로 해석된다.

---

## 1.4 Step 2: Initial Query Decomposition

첫 번째 반복에서는 원래 질의 `x`를 여러 개의 하위 검색 질의(sub-query)로 분해한다.

예를 들어 다음과 같은 질의가 있다고 하자.

```text
Alan Turing의 컴퓨터 과학 기여와 2차 세계대전에서의 역할은 무엇인가?
```

FAIR-RAG는 이를 다음과 같이 분해할 수 있다.

```text
1. Alan Turing contributions to theoretical computer science
2. Alan Turing role in breaking the Enigma code
```

이 단계의 목적은 하나의 복잡한 질의를 여러 정보 요구 단위로 나누어 검색 coverage를 높이는 것이다.

### Query Decomposition의 특징

- 원래 질의의 핵심 entity와 relation을 유지함
- 검색에 유리한 keyword-rich query로 변환함
- 최대 몇 개의 sub-query로 제한하여 검색 비용을 통제함
- multi-hop reasoning의 각 hop에 필요한 정보를 분리함

---

## 1.5 Step 3: Hybrid Retrieval

각 sub-query에 대해 검색기를 실행한다.

FAIR-RAG의 개념적 설계에서는 다음 두 검색 방식을 결합한다.

1. **Dense Retrieval**
   - 문장 또는 문서의 의미적 유사도를 embedding space에서 계산
   - paraphrase나 의미적으로 유사한 문서 검색에 강함

2. **Sparse Retrieval**
   - BM25와 같은 keyword 기반 검색
   - 고유명사, 숫자, 정확한 용어 매칭에 강함

두 검색 결과는 **Reciprocal Rank Fusion(RRF)** 등의 방식으로 결합될 수 있다.

RRF의 일반적 형태는 다음과 같다.

```text
score(d) = Σ 1 / (k + rank_i(d))
```

여기서 `rank_i(d)`는 검색기 `i`에서 문서 `d`의 순위이고, `k`는 순위 차이를 완화하기 위한 상수이다.

이 과정을 통해 dense search의 의미적 확장성과 sparse search의 정확 매칭 장점을 함께 활용할 수 있다.

---

## 1.6 Step 4: Evidence Filtering

검색된 문서가 모두 최종 답변에 유용한 것은 아니다. FAIR-RAG는 검색 결과를 바로 generator에 넣지 않고, 먼저 evidence filtering을 수행한다.

Evidence Filtering의 역할은 다음과 같다.

- 원래 질의와 무관한 문서 제거
- 주변적으로만 관련 있는 문서 제거
- 중복 문서 제거
- 잘못된 entity에 관한 문서 제거
- 답변 생성에 방해가 되는 noise 감소

이 단계는 최종 context의 **signal-to-noise ratio**를 높이는 역할을 한다.

다만 filtering이 너무 강하면 실제로 필요한 문서까지 제거할 수 있다. 따라서 evidence filtering은 precision과 recall 사이의 trade-off를 가진다.

---

## 1.7 Step 5: Structured Evidence Assessment(SEA)

FAIR-RAG의 가장 중요한 모듈은 **Structured Evidence Assessment(SEA)**이다.

SEA는 현재까지 수집된 증거가 질의의 요구사항을 충분히 만족하는지 평가한다. 단순히 “충분함/부족함”만 판단하는 것이 아니라, 질의를 요구 정보 단위로 분해하고 각 항목의 충족 여부를 점검한다.

### SEA의 입력

```text
- 원래 사용자 질의 x
- 현재까지 수집된 증거 집합 Eagg
- 이전 검색 질의 목록 Qprevious
```

### SEA의 출력

```text
- Required Findings
- Confirmed Findings
- Remaining Gaps
- is_sufficient: Yes / No
- analysis_summary
```

---

## 1.8 SEA 작동 방식

### Step 1. Required Findings 생성

SEA는 먼저 원래 질의를 답하기 위해 반드시 필요한 정보 항목으로 분해한다.

예를 들어 다음 질의가 있다고 하자.

```text
Mona Lisa가 있는 건물과 Rosetta Stone이 있는 런던 박물관의 건축 양식을 비교하라.
```

필요한 정보는 다음과 같다.

```text
1. Mona Lisa가 보관된 기관 식별
2. 해당 기관 또는 건물의 건축 양식 식별
3. Rosetta Stone이 보관된 런던 박물관 식별
4. 해당 박물관의 건축 양식 식별
5. 두 건축 양식의 비교
```

이 목록이 **Required Findings**이다.

---

### Step 2. Confirmed Findings 추출

현재까지 검색된 증거 `Eagg`를 바탕으로 이미 확인된 정보를 추출한다.

예를 들어 검색 결과에서 다음 사실이 확인되었다고 하자.

```text
- Mona Lisa는 Louvre Museum에 보관되어 있음
- Rosetta Stone은 British Museum에 보관되어 있음
```

그러면 SEA는 이를 Confirmed Findings로 기록한다.

---

### Step 3. Remaining Gaps 식별

아직 증거로 확인되지 않은 항목을 Remaining Gaps로 정리한다.

위 예시에서는 다음이 남은 gap이 된다.

```text
- Louvre Museum의 건축 양식
- British Museum의 건축 양식
- 두 건축 양식의 비교 근거
```

---

### Step 4. Sufficiency 판단

모든 Required Findings가 충분히 채워졌으면 SEA는 다음을 반환한다.

```text
is_sufficient = Yes
```

그렇지 않으면 다음을 반환한다.

```text
is_sufficient = No
```

`No`가 반환되면 FAIR-RAG는 최종 답변을 생성하지 않고, 다음 단계에서 refined query를 만든다.

---

## 1.9 Step 6: Adaptive Query Refinement

SEA가 증거 부족을 판단하면, FAIR-RAG는 Remaining Gaps를 기반으로 새로운 검색 질의를 만든다.

예를 들어 원래 질문이 다음과 같다고 하자.

```text
Enigma code를 해독한 lead scientist가 묻힌 도시는 어디인가?
```

1차 검색 후 SEA가 다음과 같이 판단했다고 하자.

```text
Confirmed Findings:
- Enigma code 해독의 주요 인물은 Alan Turing임

Remaining Gaps:
- Alan Turing의 burial place가 필요함
```

그러면 query refinement는 다음과 같은 검색 질의를 생성한다.

```text
1. Alan Turing burial place
2. city where Alan Turing is buried
```

이 방식의 핵심은 “이전 답변 전체를 다시 검색 질의로 사용하는 것”이 아니라, **부족한 정보만 겨냥하는 검색 질의**를 생성한다는 점이다.

---

## 1.10 Step 7: 반복 루프

FAIR-RAG는 다음 조건 중 하나가 만족될 때까지 반복한다.

```text
1. SEA가 is_sufficient = Yes를 반환함
2. 최대 반복 횟수에 도달함
```

일반적으로 최대 반복 횟수는 3회 정도로 설정된다.

반복 횟수가 너무 적으면 복잡한 질의에 필요한 증거를 충분히 모으지 못할 수 있다. 반대로 반복 횟수가 너무 많으면 다음 문제가 발생한다.

- 검색 비용 증가
- token 사용량 증가
- latency 증가
- irrelevant evidence 유입
- noise 증가
- 잘못된 refinement로 인한 drift

따라서 FAIR-RAG는 반복 검색의 이점을 활용하되, resource cost와 noise 증가를 제한하는 구조를 갖는다.

---

## 1.11 Step 8: Faithful Answer Generation

SEA가 증거가 충분하다고 판단하면 최종 답변 생성 단계로 이동한다.

이때 generator는 다음 원칙을 따라야 한다.

```text
- 제공된 증거에 기반해서만 답변 생성
- 근거 없는 추측 금지
- evidence에 없는 정보 삽입 금지
- 가능한 경우 source reference 포함
- 증거가 부족하면 부족하다고 명시
```

따라서 FAIR-RAG의 최종 generation은 일반 LLM 답변 생성이 아니라, **evidence-grounded faithful generation**에 가깝다.

---

## 1.12 FAIR-RAG 방법론의 의사코드

```text
Input:
  x: user query
  C: external corpus
  R: retriever
  G: generator LLM
  max_iter: maximum iteration count

Initialize:
  Eagg = ∅
  Qprevious = {x}

Step 1: Route query
  query_type = Router(x)

Step 2: If query is obvious
  return G(x)

Step 3: Iterative retrieval loop
  for i in 1 ... max_iter:

      if i == 1:
          Q = Decompose(x)
      else:
          Q = RefineQuery(x, Qprevious, RemainingGaps, ConfirmedFindings)

      Dcandidate = Retrieve(R, Q, C)
      Enew = EvidenceFilter(Dcandidate, x)
      Eagg = Eagg ∪ Enew

      Assessment = SEA(x, Eagg)

      if Assessment.is_sufficient == Yes:
          break

      Qprevious = Qprevious ∪ Q

Step 4: Final answer generation
  answer = FaithfulGenerate(x, Eagg, Assessment)

Output:
  answer
```

---

## 1.13 FAIR-RAG의 방법론적 의미

FAIR-RAG의 핵심 방법론적 가치는 다음과 같다.

1. **검색을 반복한다는 점보다, 반복의 이유를 명시한다는 점이 중요함**
   - 단순 반복 검색이 아니라 SEA가 식별한 gap을 근거로 반복함

2. **질의 중심 RAG에서 증거 중심 RAG로 이동함**
   - 기존 RAG는 “질의와 관련 있는 문서”를 찾음
   - FAIR-RAG는 “답변에 필요한 증거가 충분한가”를 판단함

3. **RAG pipeline의 해석 가능성을 높임**
   - Required Findings, Confirmed Findings, Remaining Gaps가 명시되므로 시스템의 판단 과정을 추적할 수 있음

4. **multi-hop QA에 적합함**
   - 여러 entity와 relation을 순차적으로 추적해야 하는 문제에 강함

---

# 2. DCCD 방법론 상세 정리

## 2.1 방법론의 핵심 아이디어

**Draft-Conditioned Constrained Decoding(DCCD)**은 구조화 출력 생성에서 기존 constrained decoding의 한계를 해결하기 위한 방법이다.

기존 constrained decoding은 JSON, grammar, API schema 등에서 허용되는 token만 생성하도록 강제한다. 이 방식은 구조적 유효성은 보장하지만, 모델이 원래 하려던 의미적 추론을 방해할 수 있다.

DCCD의 핵심 아이디어는 다음과 같다.

> 먼저 제약 없이 자유롭게 draft를 생성하여 의미적 계획을 만들고, 그 draft를 조건으로 constrained decoding을 수행한다.

즉, DCCD는 다음 두 과정을 분리한다.

```text
1. Semantic Planning: 자유 형식 draft 생성
2. Structural Enforcement: draft를 참고하여 구조 제약을 만족하는 최종 출력 생성
```

---

## 2.2 기존 Constrained Decoding 문제 정의

LLM의 일반적인 autoregressive generation은 다음과 같이 표현된다.

```math
ρ_θ(z_{1:T} | x) = ∏_{t=1}^{T} π_θ(z_t | h_t)
```

여기서:

```text
x: 입력 prompt
z_{1:T}: 출력 token sequence
h_t = (x, z_{<t}): 현재 decoding history
π_θ(z_t | h_t): 다음 token에 대한 모델 확률분포
```

구조화 출력에서는 최종 출력이 특정 valid set에 속해야 한다.

```math
L(x) ⊆ V^*
```

여기서 `L(x)`는 JSON schema, grammar, API signature 등을 만족하는 모든 valid sequence의 집합이다.

---

## 2.3 Valid Token Set

각 decoding step에서 허용되는 다음 token 집합은 다음과 같이 정의된다.

```math
A(h_t) = { a ∈ V : ∃ z_{t+1:T} such that (z_{<t}, a, z_{t+1:T}) ∈ L(x) }
```

즉, 현재 prefix 뒤에 token `a`를 붙였을 때 최종적으로 valid output으로 완성될 수 있다면, `a`는 허용되는 token이다.

예를 들어 JSON 출력이 필요한 경우, 현재 prefix가 다음과 같다고 하자.

```json
{
```

그러면 다음 token으로 허용될 가능성이 높은 것은 다음과 같다.

```text
"answer"
"steps"
공백 token
```

반면 일반 자연어 단어나 닫는 괄호 등은 현재 prefix에서 invalid일 수 있다.

---

## 2.4 표준 Constrained Decoding

표준 constrained decoding은 invalid token을 제거하고, valid token에 대해서만 확률을 재정규화한다.

```math
q(z_t | h_t) = \frac{π_θ(z_t | h_t) · I[z_t ∈ A(h_t)]}{α(h_t)}
```

여기서 feasible mass는 다음과 같다.

```math
α(h_t) = Σ_{a ∈ A(h_t)} π_θ(a | h_t)
```

즉, `α(h_t)`는 현재 모델이 구조적으로 허용되는 token 전체에 부여한 확률 질량이다.

---

## 2.5 Projection Tax

논문은 constrained decoding을 reverse-KL projection으로 해석한다.

표준 CD는 원래 모델 분포 `π_θ`를 valid token simplex 위로 projection한다.

```math
q(· | h_t) = argmin_{p ∈ Δ_{A(h_t)}} KL(p || π_θ(· | h_t))
```

이때 per-step distortion은 다음과 같다.

```math
KL(q(· | h_t) || π_θ(· | h_t)) = log(1 / α(h_t))
```

따라서 `α(h_t)`가 낮을수록 distortion이 커진다.

예를 들어 모델이 현재 시점에서 valid token 전체에 0.01의 확률만 부여했다면, constrained decoding은 나머지 0.99의 확률 질량을 제거하고 0.01 안에서만 재정규화한다. 이는 모델의 원래 분포를 크게 왜곡한다.

sequence-level cumulative projection tax는 다음과 같이 표현된다.

```math
KL(ρ_q(· | x) || ρ_θ(· | x))
= E_{z ~ ρ_q(· | x)} [ Σ_t log(1 / α(h_t)) ]
```

즉, generation 과정에서 feasible mass가 낮은 step이 많을수록 누적 왜곡이 커진다.

---

## 2.6 DCCD의 핵심 관찰

DCCD는 다음 사실에 주목한다.

> valid token set은 constraint에 의해 정해지지만, valid token에 대한 모델의 확률은 context에 따라 달라진다.

기존 CD는 다음 분포를 사용한다.

```math
π_θ(a | h_t)
```

DCCD는 draft `d`를 추가 context로 제공하여 다음 분포를 사용한다.

```math
π_θ(a | h_t, d)
```

이에 따라 feasible mass는 다음과 같이 변한다.

```math
α(h_t; d) = Σ_{a ∈ A(h_t)} π_θ(a | h_t, d)
```

즉, draft가 있으면 모델은 구조적으로 허용되는 token에 더 높은 확률을 줄 가능성이 커진다. 결과적으로 constrained decoding에서 발생하는 projection tax가 감소한다.

---

## 2.7 DCCD 전체 파이프라인

DCCD는 두 단계로 구성된다.

```text
[1] Unconstrained Draft Generation
        ↓
[2] Draft-Conditioned Constrained Decoding
        ↓
[3] Valid Structured Output
```

---

## 2.8 Step 1: Unconstrained Draft Generation

먼저 draft model이 입력 `x`에 대해 자유 형식 draft `y`를 생성한다.

```math
y ~ p_draft(· | x)
```

이 draft는 구조 제약을 만족할 필요가 없다.

Draft에는 다음이 포함될 수 있다.

- 문제 풀이 과정
- 중간 계산
- reasoning trace
- 최종 답 후보
- 출력 schema에 들어갈 핵심 의미 정보
- API 호출에 필요한 argument 후보

예를 들어 GSM8K 수학 문제에서 draft는 다음과 같은 자연어 풀이일 수 있다.

```text
하루에 낳는 알은 16개이다. 아침에 3개를 먹고, 머핀에 4개를 사용하므로 남는 알은 9개이다. 개당 2달러에 팔면 하루 수입은 18달러이다.
```

이 draft는 JSON이 아니지만, 최종 구조화 출력에 필요한 의미 정보를 포함한다.

---

## 2.9 Step 2: Draft-Conditioned Constrained Decoding

이후 projector model은 입력 prompt `x`, draft `y`, 현재까지 생성한 final output prefix `z_{<t}`를 모두 조건으로 사용한다.

```math
\tilde{h}_t = (x, y, z_{<t})
```

projector model의 다음 token 분포는 다음과 같다.

```math
p_2(z_t | \tilde{h}_t)
```

하지만 최종 출력은 여전히 hard constraint를 만족해야 하므로, valid token set `A(h_t)`에 기반해 masking한다.

```math
\tilde{q}(z_t | \tilde{h}_t)
= \frac{p_2(z_t | \tilde{h}_t) · I[z_t ∈ A(h_t)]}{\tilde{α}(\tilde{h}_t)}
```

여기서 draft-conditioned feasible mass는 다음과 같다.

```math
\tilde{α}(\tilde{h}_t)
= Σ_{a ∈ A(h_t)} p_2(a | \tilde{h}_t)
```

중요한 점은 constraint 자체는 바뀌지 않는다는 것이다.

```text
바뀌는 것: valid token에 대한 모델의 확률분포
바뀌지 않는 것: grammar/schema가 허용하는 token set
```

즉, DCCD는 제약을 약하게 만드는 방식이 아니라, 모델이 제약을 더 자연스럽게 따르도록 context를 보강하는 방식이다.

---

## 2.10 Best-of-K Draft Selection

DCCD는 여러 개의 draft를 생성한 뒤 가장 좋은 draft를 선택하는 방식으로 확장될 수 있다.

```math
y^{(1)}, ..., y^{(K)} ~ p_draft(· | x)
```

각 draft에 대해 constrained decoding을 수행하고, trajectory의 cumulative log feasible mass를 계산한다.

```math
S^{(k)} = Σ_t log \tilde{α}^{(k)}_t
```

이후 다음 기준으로 draft를 선택한다.

```math
k^* = argmax_k S^{(k)}
```

즉, constrained decoding 과정에서 valid token에 대한 확률 질량이 가장 높았던 draft를 선택한다.

이 기준은 다음 의미를 가진다.

- valid token이 자연스럽게 높은 확률을 받음
- constraint에 의한 강제 projection이 작음
- 구조화 출력으로 변환하기 쉬운 draft임

다만 feasible mass가 높다고 항상 의미적으로 정답이라는 보장은 없으므로, 향후에는 다음 기준과 결합할 수 있다.

- external verifier score
- majority voting
- symbolic executor feedback
- unit test result
- answer consistency
- task-specific reward model

---

## 2.11 DCCD 방법론의 의사코드

```text
Input:
  x: input prompt
  L(x): structural constraint set
  p_draft: draft model
  p_proj: projector model
  K: number of drafts

Step 1: Generate drafts
  for k in 1 ... K:
      y_k ~ p_draft(. | x)

Step 2: For each draft, perform constrained decoding
  for k in 1 ... K:
      z_k = empty sequence
      score_k = 0

      for t in 1 ... T:
          h_tilde = (x, y_k, z_{<t})
          A_t = ValidNextTokens(z_{<t}, L(x))

          p = p_proj(. | h_tilde)
          q = MaskAndRenormalize(p, A_t)

          z_t ~ q
          z_k.append(z_t)

          alpha_t = Σ_{a in A_t} p(a | h_tilde)
          score_k += log(alpha_t)

          if z_k is complete:
              break

Step 3: Select output
  k* = argmax_k score_k
  return z_{k*}
```

---

## 2.12 DCCD의 평가 설계

DCCD는 구조화 generation이 필요한 여러 유형의 benchmark에서 평가된다.

| 데이터셋 | 과제 유형 | 구조 제약 |
|---|---|---|
| **GSM8K** | 수학 word problem | JSON schema |
| **MATH500** | 고난도 수학 문제 | JSON schema |
| **GSM-Symbolic** | symbolic mathematical reasoning | expression grammar |
| **FOLIO / P-FOLIO** | first-order logic formalization | FOL grammar |

평가 기준은 **strict structured accuracy**이다.

성공으로 인정되려면 다음 두 조건을 모두 만족해야 한다.

```text
1. 최종 답이 정답과 의미적으로 일치함
2. 출력이 지정된 구조 제약을 완전히 만족함
```

따라서 답이 맞아도 JSON이 깨지면 실패이고, JSON이 맞아도 답이 틀리면 실패이다.

---

## 2.13 DCCD 방법론의 의미

DCCD의 방법론적 가치는 다음과 같다.

1. **의미 계획과 구조 제약을 분리함**
   - 기존 CD는 reasoning과 formatting을 동시에 강제함
   - DCCD는 먼저 자유롭게 reasoning한 뒤 구조화함

2. **Constrained decoding의 분포 왜곡을 줄임**
   - draft conditioning으로 feasible mass를 높임
   - projection tax를 감소시킴

3. **Training-free 방식임**
   - 별도 fine-tuning 없이 inference 단계에서 적용 가능함

4. **구조적 유효성을 유지함**
   - 최종 단계에서는 여전히 hard constraint를 적용하므로 JSON/schema/grammar validity를 보장함

5. **작은 모델의 활용 가능성을 높임**
   - draft model과 projector model을 분리하여 parameter efficiency를 높일 수 있음

---

# 3. 두 논문의 방법론 비교

## 3.1 핵심 문제의 차이

| 항목 | FAIR-RAG | DCCD |
|---|---|---|
| 해결 문제 | RAG에서 증거 부족과 hallucination 문제 | constrained decoding에서 의미 정확성 저하 문제 |
| 주요 대상 | 검색 기반 질의응답 | 구조화 출력 생성 |
| 핵심 병목 | 필요한 증거를 충분히 찾지 못함 | hard constraint가 모델 분포를 왜곡함 |
| 해결 전략 | 증거 평가 후 부족한 정보 재검색 | 자유 draft 생성 후 구조화 decoding |

---

## 3.2 방법론 구조 비교

| 항목 | FAIR-RAG | DCCD |
|---|---|---|
| 전체 구조 | 반복적 검색·평가·개선 루프 | 2단계 draft-then-constrain 구조 |
| 핵심 모듈 | SEA | Draft-conditioned projection |
| 중간 산출물 | Required Findings, Confirmed Findings, Remaining Gaps | Unconstrained draft |
| 제어 방식 | 증거 충분성 기반 반복 제어 | draft 기반 feasible mass 증가 |
| 최종 목표 | 근거 기반 faithful answer | valid and semantically correct structured output |

---

## 3.3 공통점

두 논문은 문제 영역은 다르지만 공통된 철학을 가진다.

### 1. 한 번에 답하지 않고 중간 단계를 둔다

FAIR-RAG는 최종 답변 전에 evidence assessment를 수행한다.  
DCCD는 최종 구조화 출력 전에 unconstrained draft를 생성한다.

즉, 두 방법 모두 다음 구조를 따른다.

```text
중간 사고/평가 단계 → 최종 출력 단계
```

---

### 2. LLM의 직접 생성을 보완한다

FAIR-RAG는 LLM이 검색 문서를 바로 읽고 답하는 방식을 보완한다.  
DCCD는 LLM이 constrained decoding으로 바로 구조화 답을 만드는 방식을 보완한다.

두 방법 모두 LLM의 단일 pass 생성이 불안정하다는 전제에서 출발한다.

---

### 3. Faithfulness 또는 correctness를 높이기 위한 구조적 장치를 둔다

FAIR-RAG는 증거 기반 답변 충실성을 높이고, DCCD는 구조화 출력에서 의미 정확성을 높인다.

두 방법 모두 단순 prompt engineering보다 더 구조적인 inference-time algorithm을 제안한다.

---

## 3.4 차이점

### FAIR-RAG는 외부 지식 검색 문제에 초점을 둔다

FAIR-RAG의 핵심은 “정보가 충분한가?”이다. 따라서 검색된 evidence가 중심이다.

```text
질의 → 검색 → 증거 평가 → 부족한 정보 검색 → 답변
```

### DCCD는 출력 형식 제약 문제에 초점을 둔다

DCCD의 핵심은 “구조를 강제하면서 의미를 잃지 않는가?”이다. 따라서 decoding distribution이 중심이다.

```text
질의 → 자유 draft → 제약 decoding → 구조화 출력
```

---

## 3.5 방법론적 관점에서의 종합 평가

FAIR-RAG와 DCCD는 모두 inference-time에서 LLM의 약점을 보완하는 방법이다. 그러나 보완하는 지점은 다르다.

- FAIR-RAG는 **검색과 증거 수집 과정**을 보완한다.
- DCCD는 **출력 생성과 decoding 과정**을 보완한다.

두 방법을 함께 보면, 최근 LLM 연구의 중요한 흐름을 확인할 수 있다.

> LLM 성능 향상은 단순히 모델 크기나 prompt 품질만의 문제가 아니라, inference 과정 자체를 어떻게 구조화하느냐의 문제이다.

FAIR-RAG는 RAG pipeline을 증거 평가 중심으로 구조화하고, DCCD는 constrained decoding을 draft-conditioned projection으로 구조화한다. 둘 다 LLM을 단순 generator로 쓰는 것이 아니라, **계획, 평가, 검증, 제약 적용을 분리한 시스템 구성요소**로 활용한다는 점에서 방법론적 의의가 크다.

---

# 4. 핵심 요약

## FAIR-RAG 방법론 요약

```text
사용자 질의
→ 질의 난이도 routing
→ query decomposition
→ retrieval
→ evidence filtering
→ SEA로 증거 충분성 평가
→ 부족한 gap 기반 query refinement
→ 반복 검색
→ faithful answer generation
```

FAIR-RAG의 핵심은 **Structured Evidence Assessment(SEA)**이다. SEA는 질의를 Required Findings로 분해하고, 현재 증거가 어떤 항목을 충족했는지 평가하며, 남은 Remaining Gaps를 다음 검색 질의로 연결한다.

---

## DCCD 방법론 요약

```text
입력 prompt
→ unconstrained draft generation
→ draft를 context로 추가
→ grammar/schema 기반 constrained decoding
→ valid structured output
```

DCCD의 핵심은 **semantic planning과 structural enforcement의 분리**이다. 자유 draft가 모델의 의미적 추론을 먼저 확보하고, 이후 constrained decoding이 구조적 유효성을 보장한다.

---

# 5. 결론

두 논문의 방법론은 서로 다른 문제를 다루지만, 공통적으로 **LLM의 단일 단계 생성 방식이 가진 불안정성을 inference-time 구조화로 해결**하려는 접근이다.

FAIR-RAG는 RAG에서 “필요한 증거가 충분한가?”를 명시적으로 점검함으로써 검색 품질과 답변 충실성을 높인다. DCCD는 structured generation에서 “형식을 강제하는 과정이 의미를 훼손하지 않는가?”를 문제로 보고, draft conditioning을 통해 constrained decoding의 분포 왜곡을 줄인다.

따라서 두 연구는 모두 향후 LLM 시스템 설계에서 중요한 시사점을 제공한다.

```text
FAIR-RAG: 검색-증거-답변 생성의 구조화
DCCD: 사고-제약-구조화 출력의 구조화
```

궁극적으로 두 논문은 LLM을 단순한 텍스트 생성기가 아니라, **계획·검색·평가·구조화·검증을 포함한 복합 추론 시스템의 구성 요소**로 다루어야 함을 보여준다.
