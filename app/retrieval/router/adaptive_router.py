from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ComplexityLevel = Literal["low", "medium", "high"]
RetrievalPolicy = Literal["admin_policy", "field_ops", "general"]
DEFAULT_COMPLEXITY_LEVEL: ComplexityLevel = "medium"


@dataclass(frozen=True)
class AppliedParams:
    top_k: int
    snippet_max_chars: int
    chunk_policy: Literal["compact", "balanced", "expanded"]


@dataclass(frozen=True)
class RoutingDecision:
    route_key: str
    strategy_id: str
    applied_params: AppliedParams
    route_reason: str
    retrieval_policy: RetrievalPolicy


ROUTING_PARAMS_BY_COMPLEXITY: dict[ComplexityLevel, AppliedParams] = {
    "low": AppliedParams(top_k=4, snippet_max_chars=400, chunk_policy="compact"),
    "medium": AppliedParams(top_k=6, snippet_max_chars=700, chunk_policy="balanced"),
    "high": AppliedParams(top_k=9, snippet_max_chars=1100, chunk_policy="expanded"),
}

RETRIEVAL_POLICY_BY_TOPIC: dict[str, RetrievalPolicy] = {
    "welfare": "admin_policy",
    "traffic": "field_ops",
    "environment": "field_ops",
    "construction": "field_ops",
    "general": "general",
}


class AdaptiveRouter:
    def route(self, topic_type: str, complexity_level: str, complexity_score: float) -> RoutingDecision:
        normalized_topic = _normalize_topic_type(topic_type)
        normalized_level = _normalize_complexity_level(complexity_level)
        safe_score = max(0.0, min(1.0, float(complexity_score)))

        applied = ROUTING_PARAMS_BY_COMPLEXITY[normalized_level]
        route_key = build_route_key(normalized_topic, normalized_level)
        strategy_id = build_strategy_id(normalized_topic, normalized_level)
        retrieval_policy = resolve_retrieval_policy(normalized_topic)
        route_reason = (
            f"{normalized_topic} 주제에서 complexity={normalized_level} "
            f"(score={safe_score:.3f})로 판단하여 "
            f"top_k={applied.top_k}, snippet_max_chars={applied.snippet_max_chars}, "
            f"chunk_policy={applied.chunk_policy}, retrieval_policy={retrieval_policy}를 적용했습니다."
        )

        return RoutingDecision(
            route_key=route_key,
            strategy_id=strategy_id,
            applied_params=applied,
            route_reason=route_reason,
            retrieval_policy=retrieval_policy,
        )


def route(topic_type: str, complexity_level: str, complexity_score: float) -> RoutingDecision:
    return _DEFAULT_ROUTER.route(
        topic_type=topic_type,
        complexity_level=complexity_level,
        complexity_score=complexity_score,
    )


def parse_route_key(route_key: str) -> tuple[str, ComplexityLevel]:
    raw = str(route_key or "").strip()
    if "/" not in raw:
        return "general", DEFAULT_COMPLEXITY_LEVEL

    topic, complexity = raw.split("/", 1)
    normalized_topic = _normalize_topic_type(topic)
    normalized_level = _normalize_complexity_level(complexity)
    return normalized_topic, normalized_level


def build_route_key(topic_type: str, complexity_level: str) -> str:
    return f"{_normalize_topic_type(topic_type)}/{_normalize_complexity_level(complexity_level)}"


def build_strategy_id(topic_type: str, complexity_level: str) -> str:
    topic, level = parse_route_key(build_route_key(topic_type, complexity_level))
    return f"topic_{topic}_{level}_v1"


def resolve_retrieval_policy(topic_type: str) -> RetrievalPolicy:
    return RETRIEVAL_POLICY_BY_TOPIC.get(_normalize_topic_type(topic_type), "general")


def _normalize_topic_type(topic_type: str) -> str:
    cleaned = str(topic_type or "").strip().lower()
    return cleaned or "general"


def _normalize_complexity_level(level: str) -> ComplexityLevel:
    normalized = str(level or "").strip().lower()
    if normalized in ROUTING_PARAMS_BY_COMPLEXITY:
        return normalized  # type: ignore[return-value]
    return DEFAULT_COMPLEXITY_LEVEL


_DEFAULT_ROUTER = AdaptiveRouter()
