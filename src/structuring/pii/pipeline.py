from __future__ import annotations

import logging
from typing import Any

from src.pii.ko_pii_adapter import KoPiiAdapter
from src.pii.postcheck import postcheck_text, redact_address_and_vehicle
from src.structuring.pii.risk_policy import (
    PiiPipelineDecision,
    detect_review_risks,
    finding_to_dict,
    passed,
    quarantined,
    review,
)


class PiiSanitizationPipeline:
    """RAG/임베딩/LLM 입력 전에 PII가 남지 않도록 실패 닫힘으로 동작한다."""

    def __init__(
        self,
        *,
        adapter: KoPiiAdapter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.adapter = adapter or KoPiiAdapter()
        self.logger = logger or logging.getLogger(__name__)

    def sanitize_for_rag(self, text: str | None) -> PiiPipelineDecision:
        source = "" if text is None else str(text)
        self.logger.debug("PII sanitize start len=%d", len(source))
        if not source:
            return passed("", engine_summary={"empty": True})

        review_reasons = detect_review_risks(source)
        if review_reasons:
            self.logger.info("PII sanitize review reasons=%s", ",".join(review_reasons))
            return review(review_reasons)

        first_pass = self.adapter.redact(source)
        if not first_pass.ok:
            self.logger.warning("PII sanitize quarantined error=%s", first_pass.error_code)
            return quarantined([first_pass.error_code or "KO_PII_ERROR"])

        supplemental_source = redact_address_and_vehicle(source)
        second_pass = self.adapter.redact(supplemental_source)
        if not second_pass.ok:
            self.logger.warning("PII sanitize quarantined error=%s", second_pass.error_code)
            return quarantined([second_pass.error_code or "KO_PII_ERROR"])

        sanitized = redact_address_and_vehicle(second_pass.text)
        postcheck = postcheck_text(sanitized)
        if not postcheck.passed:
            findings = [
                finding_to_dict(f.label, f.reason, f.start, f.end)
                for f in postcheck.findings
            ]
            self.logger.warning("PII sanitize quarantined findings=%d", len(findings))
            return quarantined(
                ["POSTCHECK_HIGH_RISK_REMAINS"],
                findings=findings,
                engine_summary=second_pass.summary,
            )

        self.logger.debug("PII sanitize passed len=%d", len(sanitized))
        return passed(sanitized, engine_summary=second_pass.summary)


def decision_to_metadata(decision: PiiPipelineDecision) -> dict[str, Any]:
    return {
        "pii_status": decision.status.value,
        "needs_review": bool(decision.needs_review),
        "pii_reasons": list(decision.reasons),
        "pii_findings": list(decision.findings),
    }
