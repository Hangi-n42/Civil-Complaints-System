# Data Schema Spec (Pydantic + TypeScript)

문서 버전: v1.1  
기준: PRD v2.1, 사용자 시나리오 v1.1, WBS v4.1

## 1. 목적

Adaptive RAG Workbench 구현에서 백엔드(Pydantic)와 프론트엔드(TypeScript)가 동일한 데이터 계약을 사용하도록 스키마를 고정한다.  
라우팅은 `topic_type + complexity_level`을 기본 축으로 사용한다.

## 2. Analyzer Output 스키마

## 2.1 TopicAnalyzer Output

### Pydantic (Python)

```python
from pydantic import BaseModel
from typing import Literal

class TopicAnalysis(BaseModel):
  topic_type: Literal["welfare", "traffic", "environment", "construction", "general"]
    topic_confidence: float
```

### TypeScript

```ts
export type TopicType = "welfare" | "traffic" | "environment" | "construction" | "general";

export interface TopicAnalysis {
  topic_type: TopicType;
  topic_confidence: number;
}
```

## 2.2 ComplexityAnalyzer Output (신규 핵심)

### Pydantic (Python)

```python
from pydantic import BaseModel
from typing import Literal, Dict

class ComplexityAnalysis(BaseModel):
    complexity_score: float  # 0.0 ~ 1.0
    complexity_level: Literal["low", "medium", "high"]
    intent_count: int
    constraint_count: int
    entity_diversity: int
    policy_reference_count: int
    cross_sentence_dependency: bool
    complexity_trace: Dict[str, float | int | bool]
```

### TypeScript

```ts
export type ComplexityLevel = "low" | "medium" | "high";

export interface ComplexityAnalysis {
  complexity_score: number; // 0.0 ~ 1.0
  complexity_level: ComplexityLevel;
  intent_count: number;
  constraint_count: number;
  entity_diversity: number;
  policy_reference_count: number;
  cross_sentence_dependency: boolean;
  complexity_trace: Record<string, number | boolean>;
}
```

## 2.3 Unified Analyzer Output

### Pydantic (Python)

```python
from pydantic import BaseModel
from typing import Literal, List, Optional

class AnalyzerOutput(BaseModel):
  topic_type: Literal["welfare", "traffic", "environment", "construction", "general"]
    complexity_score: float
    complexity_level: Literal["low", "medium", "high"]
    intent_count: int
    constraint_count: int
    entity_diversity: int
    policy_reference_count: int
    cross_sentence_dependency: bool
    request_segments: List[str]
    # legacy/보조 표시용 (라우팅 핵심 기준 아님)
    length_bucket: Optional[Literal["short", "medium", "long"]] = None
    is_multi: Optional[bool] = None
```

### TypeScript

```ts
export interface AnalyzerOutput {
  topic_type: "welfare" | "traffic" | "environment" | "construction" | "general";
  complexity_score: number;
  complexity_level: "low" | "medium" | "high";
  intent_count: number;
  constraint_count: number;
  entity_diversity: number;
  policy_reference_count: number;
  cross_sentence_dependency: boolean;
  request_segments: string[];
  // legacy/보조 표시용 (라우팅 핵심 기준 아님)
  length_bucket?: "short" | "medium" | "long";
  is_multi?: boolean;
}
```

## 3. Complaint 데이터 모델

## 3.1 Complaint Core Model

### Pydantic (Python)

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional

class Complaint(BaseModel):
    complaint_id: str = Field(..., examples=["CMP-2026-0001"])
    title: str
    complaint_text: str
    status: Literal["pending", "in_progress", "review_completed"] = "pending"
    category: Optional[str] = None
    created_at: str  # ISO-8601 +09:00
    updated_at: Optional[str] = None
```

### TypeScript

```ts
export type ComplaintStatus = "pending" | "in_progress" | "review_completed";

export interface Complaint {
  complaint_id: string;
  title: string;
  complaint_text: string;
  status: ComplaintStatus;
  category?: string;
  created_at: string; // ISO-8601 +09:00
  updated_at?: string;
}
```

## 3.2 Workbench List Item Model

### TypeScript

```ts
export interface ComplaintListItem {
  complaint_id: string;
  title: string;
  status: "pending" | "in_progress" | "review_completed";
  topic_type?: "welfare" | "traffic" | "environment" | "construction" | "general";
  complexity_level?: "low" | "medium" | "high";
  complexity_score?: number;
}
```

## 4. Routing Trace / Hint / Structured Output 모델

## 4.1 RoutingTrace

### Pydantic (Python)

```python
from pydantic import BaseModel
from typing import Optional, Dict, List

class RoutingTrace(BaseModel):
    topic_type: str
    complexity_level: str
    complexity_score: float
    complexity_trace: Dict[str, float | int | bool]
  request_segments: List[str] = []
    route_reason: Optional[str] = None
```

### TypeScript

```ts
export interface RoutingTrace {
  topic_type: string;
  complexity_level: string;
  complexity_score: number;
  complexity_trace: Record<string, number | boolean>;
  request_segments?: string[];
  route_reason?: string;
}
```

## 4.2 RoutingHint

### Pydantic (Python)

```python
from pydantic import BaseModel

class RoutingHint(BaseModel):
    strategy_id: str
    route_key: str  # {topic_type}/{complexity_level}
    top_k: int
    snippet_max_chars: int
    chunk_policy: str
```

### TypeScript

```ts
export interface RoutingHint {
  strategy_id: string;
  route_key: string; // {topic_type}/{complexity_level}
  top_k: number;
  snippet_max_chars: number;
  chunk_policy: string;
}
```

## 4.3 StructuredOutput

### Pydantic (Python)

```python
from pydantic import BaseModel
from typing import List

class StructuredOutput(BaseModel):
    summary: str
    action_items: List[str]
    request_segments: List[str]
```

### TypeScript

```ts
export interface StructuredOutput {
  summary: string;
  action_items: string[];
  request_segments: string[];
}
```

## 5. 필수 정합성 규칙

- 라우팅 핵심 키는 `topic_type`, `complexity_level`, `complexity_score`로 고정한다.
- `route_key`는 `{topic_type}/{complexity_level}` 포맷을 사용한다.
- `length_bucket`, `is_multi`는 보조 분석/표시용으로만 사용하고 라우팅 핵심 기준으로 사용하지 않는다.
- `complaint_id`를 전 구간 식별자 키로 고정한다.
- 상태 값은 `pending | in_progress | review_completed`로 고정한다.
- `/search`, `/qa` 응답 객체에는 `routing_trace`를 항상 포함한다.
- `/qa` 응답 객체에는 `structured_output`을 항상 포함한다.