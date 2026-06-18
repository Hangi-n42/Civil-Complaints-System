"""기존 import 호환성을 위한 PublicAgencyInsightEngine 래퍼."""

from __future__ import annotations

from datetime import datetime

from app.complaint_intelligence.config import ComplaintIntelligenceConfig
from app.complaint_intelligence.embedding import EmbeddingProvider
from app.complaint_intelligence.public_insights.candidate_generator import PublicInsightCandidateGenerator
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.public_insights.service import PublicInsightService
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, IssueAlert, PublicAgencyInsight


class PublicAgencyInsightEngine:
    """기존 엔진 API를 유지하면서 새 EvidencePack 기반 서비스를 호출한다."""

    def __init__(
        self,
        config: ComplaintIntelligenceConfig | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        service: PublicInsightService | None = None,
    ) -> None:
        self.config = config
        self.embedding_provider = embedding_provider
        if service is not None:
            self.service = service
        else:
            candidate_generator = PublicInsightCandidateGenerator(
                config=config,
                embedding_provider=embedding_provider,
            )
            self.service = PublicInsightService(
                config=config,
                candidate_generator=candidate_generator,
            )

    def generate(
        self,
        events: list[ComplaintIntelligenceEvent],
        alerts: list[IssueAlert] | None = None,
        now: datetime | None = None,
    ) -> list[PublicAgencyInsight]:
        """공공기관 행정 인사이트를 생성한다."""

        return self.service.generate_insights(events, alerts, now)

    def get_evidence_pack(self, insight_id: str) -> PublicInsightEvidencePack | None:
        """생성된 인사이트의 EvidencePack을 반환한다."""

        return self.service.get_evidence_pack(insight_id)
