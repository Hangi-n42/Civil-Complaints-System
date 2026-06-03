from __future__ import annotations

from app.retrieval.router.adaptive_router import (
    DEFAULT_COMPLEXITY_LEVEL,
    ROUTING_PARAMS_BY_COMPLEXITY,
    route,
    resolve_retrieval_policy,
)


def test_route_builds_expected_keys_and_params_for_low():
    decision = route(topic_type="welfare", complexity_level="low", complexity_score=0.12)

    assert decision.route_key == "welfare/low"
    assert decision.strategy_id == "topic_welfare_low_v1"
    assert decision.applied_params.top_k == 4
    assert decision.applied_params.snippet_max_chars == 400
    assert decision.applied_params.chunk_policy == "compact"


def test_route_builds_expected_keys_and_params_for_medium_and_high():
    medium = route(topic_type="traffic", complexity_level="medium", complexity_score=0.55)
    high = route(topic_type="environment", complexity_level="high", complexity_score=0.89)

    assert medium.route_key == "traffic/medium"
    assert medium.strategy_id == "topic_traffic_medium_v1"
    assert medium.applied_params == ROUTING_PARAMS_BY_COMPLEXITY["medium"]

    assert high.route_key == "environment/high"
    assert high.strategy_id == "topic_environment_high_v1"
    assert high.applied_params == ROUTING_PARAMS_BY_COMPLEXITY["high"]


def test_route_falls_back_on_invalid_complexity_level():
    decision = route(topic_type="welfare", complexity_level="unknown", complexity_score=0.44)

    assert decision.route_key == f"welfare/{DEFAULT_COMPLEXITY_LEVEL}"
    assert decision.strategy_id == f"topic_welfare_{DEFAULT_COMPLEXITY_LEVEL}_v1"
    assert decision.applied_params == ROUTING_PARAMS_BY_COMPLEXITY[DEFAULT_COMPLEXITY_LEVEL]


def test_route_is_deterministic_for_same_input():
    first = route(topic_type="construction", complexity_level="high", complexity_score=0.9123)
    second = route(topic_type="construction", complexity_level="high", complexity_score=0.9123)

    assert first == second


def test_route_derives_topic_aware_retrieval_policy():
    welfare = route(topic_type="welfare", complexity_level="medium", complexity_score=0.52)
    traffic = route(topic_type="traffic", complexity_level="medium", complexity_score=0.52)
    general = route(topic_type="unknown", complexity_level="medium", complexity_score=0.52)

    assert welfare.retrieval_policy == "admin_policy"
    assert traffic.retrieval_policy == "field_ops"
    assert general.retrieval_policy == "general"
    assert resolve_retrieval_policy("construction") == "field_ops"
