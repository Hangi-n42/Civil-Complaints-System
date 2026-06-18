"""PublicAgencyInsight 생성 orchestration 서비스."""

from __future__ import annotations

import logging
from datetime import datetime

from app.complaint_intelligence.config import (
    ComplaintIntelligenceConfig,
    get_complaint_intelligence_config,
)
from app.complaint_intelligence.public_insights.aspect_extractor import AspectExtractor
from app.complaint_intelligence.public_insights.candidate_generator import PublicInsightCandidateGenerator
from app.complaint_intelligence.public_insights.evidence_pack import EvidencePackBuilder, PublicInsightEvidencePack
from app.complaint_intelligence.public_insights.fallback_templates import PublicInsightFallbackGenerator
from app.complaint_intelligence.public_insights.grounding_verifier import GroundingVerifier
from app.complaint_intelligence.public_insights.insight_ranker import PublicInsightRanker
from app.complaint_intelligence.public_insights.llm_provider import build_llm_provider, PublicInsightLLMProvider
from app.complaint_intelligence.public_insights.llm_synthesizer import PublicInsightLLMSynthesizer
from app.complaint_intelligence.public_insights.quality_gate import (
    InsightQualityGate,
    attach_actionability_metrics,
)
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, IssueAlert, PublicAgencyInsight


class PublicInsightService:
    """EvidencePack 기반 공공기관 인사이트 생성 기본 경로."""

    def __init__(
        self,
        config: ComplaintIntelligenceConfig | None = None,
        candidate_generator: PublicInsightCandidateGenerator | None = None,
        evidence_pack_builder: EvidencePackBuilder | None = None,
        aspect_extractor: AspectExtractor | None = None,
        llm_provider: PublicInsightLLMProvider | None = None,
        grounding_verifier: GroundingVerifier | None = None,
        insight_ranker: PublicInsightRanker | None = None,
        fallback_generator: PublicInsightFallbackGenerator | None = None,
        quality_gate: InsightQualityGate | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config or get_complaint_intelligence_config()
        self.candidate_generator = candidate_generator or PublicInsightCandidateGenerator(config=self.config)
        self.evidence_pack_builder = evidence_pack_builder or EvidencePackBuilder(config=self.config)
        self.aspect_extractor = aspect_extractor or AspectExtractor()
        provider = llm_provider or build_llm_provider(self.config)
        self.llm_synthesizer = PublicInsightLLMSynthesizer(provider)
        self.grounding_verifier = grounding_verifier or GroundingVerifier()
        self.insight_ranker = insight_ranker or PublicInsightRanker(config=self.config)
        self.fallback_generator = fallback_generator or PublicInsightFallbackGenerator()
        self.quality_gate = quality_gate or InsightQualityGate(
            min_grounding_score=self.config.public_insight_min_grounding_score,
            min_confidence=self.config.public_insight_min_confidence,
        )
        self.logger = logger or logging.getLogger(__name__)
        self._evidence_pack_by_insight_id: dict[str, PublicInsightEvidencePack] = {}

    def generate_insights(
        self,
        events: list[ComplaintIntelligenceEvent],
        issue_alerts: list[IssueAlert] | None = None,
        now: datetime | None = None,
    ) -> list[PublicAgencyInsight]:
        """공공기관 인사이트를 생성하고 중복을 제거해 우선순위순으로 반환한다."""

        if not self.config.public_insight_enabled:
            return []

        candidates = self.candidate_generator.generate(events, issue_alerts or [], now)
        insights: list[PublicAgencyInsight] = []

        for candidate in candidates:
            pack = self.evidence_pack_builder.build(candidate, events, issue_alerts or [])
            pack = self.aspect_extractor.enrich(pack)

            insight = self._generate_one(pack, now)
            if insight is not None:
                self._evidence_pack_by_insight_id[insight.insight_id] = pack
                insights.append(insight)

        return _dedupe_and_sort(insights)

    def get_evidence_pack(self, insight_id: str) -> PublicInsightEvidencePack | None:
        """생성된 인사이트의 마스킹된 EvidencePack을 debug 용도로 반환한다."""

        return self._evidence_pack_by_insight_id.get(insight_id)

    def _generate_one(
        self,
        pack: PublicInsightEvidencePack,
        now: datetime | None,
    ) -> PublicAgencyInsight | None:
        if self.config.public_insight_llm_enabled:
            try:
                draft = self.llm_synthesizer.synthesize(pack)
                verified = self.grounding_verifier.verify_and_repair(draft, pack)
                ranked = self.insight_ranker.rank(verified, pack, now)
                ranked = attach_actionability_metrics(ranked)
                if (
                    ranked.grounding_score >= self.config.public_insight_min_grounding_score
                    and ranked.confidence >= self.config.public_insight_min_confidence
                    and ranked.recommended_actions
                ):
                    gate_result = self.quality_gate.evaluate(ranked, pack)
                    if gate_result.passed:
                        return ranked
                    self.logger.warning(
                        "Public insight quality gate failed: codes=%s",
                        [failure.code for failure in gate_result.failures],
                    )
            except Exception as exc:  # noqa: BLE001 - fallback을 위한 안전 경계
                # 민원 원문/근거 텍스트는 로그에 남기지 않는다.
                self.logger.warning("Public insight LLM path failed: %s", type(exc).__name__)

        if not self.config.public_insight_fallback_on_llm_error:
            return None
        fallback = self.fallback_generator.generate(pack, reason="LLM 경로 실패 또는 품질 게이트 실패")
        ranked_fallback = attach_actionability_metrics(self.insight_ranker.rank(fallback, pack, now))
        gate_result = self.quality_gate.evaluate(ranked_fallback, pack)
        if gate_result.passed:
            return ranked_fallback
        self.logger.warning(
            "Public insight fallback discarded by quality gate: codes=%s",
            [failure.code for failure in gate_result.failures],
        )
        return None


def _dedupe_and_sort(insights: list[PublicAgencyInsight]) -> list[PublicAgencyInsight]:
    deduped: dict[str, PublicAgencyInsight] = {}
    for insight in insights:
        overlap_key = (
            insight.type,
            insight.topic,
            (insight.affected_region or {}).get("dominant_region"),
            ",".join(sorted(insight.representative_complaint_ids[:5])),
        )
        key = "|".join(str(item or "") for item in overlap_key)
        current = deduped.get(key)
        if current is None or _rank_tuple(insight) > _rank_tuple(current):
            deduped[key] = insight
    return sorted(deduped.values(), key=_rank_tuple, reverse=True)


def _rank_tuple(insight: PublicAgencyInsight) -> tuple[int, float, int]:
    priority_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}.get(insight.priority, 0)
    return (priority_rank, insight.confidence, insight.affected_count)
