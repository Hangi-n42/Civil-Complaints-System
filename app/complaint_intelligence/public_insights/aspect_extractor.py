"""민원 클러스터의 세부 불편 측면과 시민 요구를 추출한다."""

from __future__ import annotations

from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack


ASPECT_CATALOG: dict[str, list[str]] = {
    "신청 절차": ["신청", "절차", "복잡", "어려", "단계", "서류"],
    "지원 기준": ["지원", "기준", "자격", "대상", "조건", "완화", "확대"],
    "요금/비용": ["요금", "비용", "수수료", "비싸", "부담"],
    "안내 부족": ["안내", "모르", "어디", "어떻게", "필요서류", "문의"],
    "처리 지연": ["지연", "늦", "처리 안", "처리되지", "미처리", "답변 없음", "오래"],
    "현장 안전": ["위험", "사고", "꺼짐", "침하", "붕괴", "감전", "침수", "싱크홀", "구멍", "움푹"],
    "시설 파손": ["파손", "고장", "꺼짐", "깨짐", "침하", "막힘", "구멍", "움푹", "내려앉", "아스팔트"],
    "단속 공백": ["불법", "단속", "주정차", "소음", "무단투기"],
    "생활환경 불편": ["악취", "냄새", "소음", "진동"],
    "접근성/사용성": ["앱", "로그인", "예약", "결제", "불편", "어려움", "오류"],
    "소통 부족": ["진행", "상태", "담당", "기간", "왜", "연락"],
}

REQUEST_CATALOG: dict[str, tuple[str, list[str]]] = {
    "정보 제공": ("정보 제공", ["안내", "문의", "어디", "어떻게", "필요서류", "기준"]),
    "절차 개선": ("절차 개선", ["절차", "복잡", "단계", "신청"]),
    "현장 점검": ("현장 점검", ["위험", "점검", "침하", "꺼짐", "악취"]),
    "시설 보수": ("시설 보수", ["파손", "고장", "보수", "수리", "침하"]),
    "단속 강화": ("단속 강화", ["단속", "불법", "주정차", "무단투기"]),
    "기준 완화": ("기준 완화", ["기준", "완화", "자격", "조건"]),
    "지원 확대": ("지원 확대", ["지원", "확대", "대상"]),
    "서비스 개선": ("서비스 개선", ["앱", "예약", "대여", "결제", "오류", "불편"]),
    "처리 속도 개선": ("처리 속도 개선", ["지연", "늦", "오래", "처리 안"]),
    "소통 강화": ("소통 강화", ["진행", "상태", "담당", "기간", "연락"]),
}


class AspectExtractor:
    """규칙 기반 aspect/request 추출기."""

    def enrich(self, pack: PublicInsightEvidencePack) -> PublicInsightEvidencePack:
        """EvidencePack에 aspect와 시민 요구를 근거 ID와 함께 채운다."""

        data = pack.model_copy(deep=True)
        data.extracted_aspects = self.extract_aspects(pack)
        data.citizen_requests = self.extract_requests(pack)
        data.operational_metrics = {
            **data.operational_metrics,
            **_confidence_metrics(data.extracted_aspects, data.citizen_requests),
        }
        return data

    def extract_aspects(self, pack: PublicInsightEvidencePack) -> list[dict]:
        aspects: list[dict] = []
        for aspect, keywords in ASPECT_CATALOG.items():
            evidence_ids: list[str] = []
            phrases: list[str] = []
            confidences: list[float] = []
            evidence_spans: list[dict] = []
            for complaint in pack.representative_complaints:
                matched = _first_matching_source(complaint, ("observation", "result", "context", "request"), keywords)
                if matched is None:
                    continue
                matched_text, source_field, source_payload = matched
                ids = _evidence_ids(complaint)
                evidence_ids.extend(ids)
                phrases.append(_short_phrase(matched_text))
                confidences.append(_source_confidence(source_payload, source_field))
                evidence_spans.extend(_source_spans(ids, source_field, source_payload))
            if evidence_ids:
                aspects.append(
                    {
                        "aspect": aspect,
                        "count": len(set(evidence_ids)),
                        "sentiment": "negative",
                        "evidence_ids": sorted(set(evidence_ids)),
                        "representative_phrases": _dedupe(phrases)[:3],
                        "confidence": _aggregate_confidence(
                            confidences,
                            covered_count=len(set(evidence_ids)),
                            total_count=pack.complaint_count,
                            span_count=len(evidence_spans),
                        ),
                        "evidence_spans": evidence_spans,
                    }
                )
        return sorted(aspects, key=lambda item: item["count"], reverse=True)

    def extract_requests(self, pack: PublicInsightEvidencePack) -> list[dict]:
        buckets: dict[str, dict[str, object]] = {}
        for complaint in pack.representative_complaints:
            request_text = _structured_text(complaint, "request")
            for request, (request_type, keywords) in REQUEST_CATALOG.items():
                matched = _first_matching_source(complaint, ("request",), keywords)
                if matched is None:
                    continue
                matched_text, source_field, source_payload = matched
                bucket = buckets.setdefault(
                    request_type,
                    {
                        "request": _request_label(request_type, matched_text),
                        "request_type": request_type,
                        "evidence_ids": set(),
                        "confidences": [],
                        "evidence_spans": [],
                    },
                )
                evidence_ids = bucket["evidence_ids"]
                ids = _evidence_ids(complaint)
                if isinstance(evidence_ids, set):
                    evidence_ids.update(ids)
                confidences = bucket["confidences"]
                if isinstance(confidences, list):
                    confidences.append(_source_confidence(source_payload, source_field))
                spans = bucket["evidence_spans"]
                if isinstance(spans, list):
                    spans.extend(_source_spans(ids, source_field, source_payload))

        requests: list[dict] = []
        for bucket in buckets.values():
            evidence_ids = bucket.get("evidence_ids")
            if not isinstance(evidence_ids, set) or not evidence_ids:
                continue
            requests.append(
                {
                    "request": str(bucket.get("request") or bucket.get("request_type")),
                    "count": len(evidence_ids),
                    "evidence_ids": sorted(evidence_ids),
                    "request_type": str(bucket.get("request_type")),
                    "confidence": _aggregate_confidence(
                        bucket.get("confidences") if isinstance(bucket.get("confidences"), list) else [],
                        covered_count=len(evidence_ids),
                        total_count=pack.complaint_count,
                        span_count=len(bucket.get("evidence_spans") if isinstance(bucket.get("evidence_spans"), list) else []),
                    ),
                    "evidence_spans": bucket.get("evidence_spans") if isinstance(bucket.get("evidence_spans"), list) else [],
                }
            )
        return sorted(requests, key=lambda item: item["count"], reverse=True)


def _short_phrase(text: str) -> str:
    cleaned = " ".join(text.split())
    return cleaned[:80]


def _priority_texts(complaint: dict, fields: tuple[str, ...]) -> list[str]:
    structured = [_structured_text(complaint, field) for field in fields]
    structured = [text for text in structured if text]
    if structured:
        return structured
    return [str(complaint.get("masked_text") or "")]


def _first_matching_source(
    complaint: dict,
    fields: tuple[str, ...],
    keywords: list[str],
) -> tuple[str, str, dict] | None:
    for field in fields:
        payload = _structured_payload(complaint, field)
        text = str(payload.get("text") or "").strip()
        if text and any(keyword in text for keyword in keywords):
            return text, field, payload

    masked_text = str(complaint.get("masked_text") or "")
    if masked_text and any(keyword in masked_text for keyword in keywords):
        return masked_text, "masked_text", {}
    return None


def _evidence_ids(complaint: dict) -> list[str]:
    source_ids = complaint.get("source_complaint_ids")
    if isinstance(source_ids, list) and source_ids:
        return [str(item) for item in source_ids if str(item)]
    complaint_id = complaint.get("complaint_id")
    return [str(complaint_id)] if complaint_id else []


def _structured_text(complaint: dict, field: str) -> str:
    return str(_structured_payload(complaint, field).get("text") or "").strip()


def _structured_payload(complaint: dict, field: str) -> dict:
    elements = complaint.get("structured_elements") or {}
    if not isinstance(elements, dict):
        return {}
    value = elements.get(field) or {}
    if not isinstance(value, dict):
        return {}
    return value


def _source_confidence(source_payload: dict, source_field: str) -> float:
    if source_field == "masked_text":
        return 0.55
    value = source_payload.get("confidence")
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return 0.72 if source_payload.get("evidence_span") else 0.65


def _source_spans(evidence_ids: list[str], source_field: str, source_payload: dict) -> list[dict]:
    span = source_payload.get("evidence_span")
    if not isinstance(span, list) or len(span) != 2:
        return []
    return [
        {
            "complaint_id": evidence_id,
            "field": source_field,
            "evidence_span": list(span),
        }
        for evidence_id in evidence_ids
    ]


def _first_matching_text(texts: list[str], keywords: list[str]) -> str:
    for text in texts:
        if any(keyword in text for keyword in keywords):
            return text
    return ""


def _request_label(request_type: str, text: str) -> str:
    cleaned = _short_phrase(text)
    if request_type in cleaned:
        return request_type
    if request_type == "절차 개선" and "신청" in cleaned:
        return "신청 절차 개선"
    if request_type == "기준 완화" and "지원" in cleaned:
        return "지원 기준 완화"
    return request_type


def _avg(values: list[float] | object) -> float | None:
    if not isinstance(values, list) or not values:
        return None
    return round(sum(float(value) for value in values) / len(values), 4)


def _aggregate_confidence(
    values: list[float] | object,
    *,
    covered_count: int,
    total_count: int,
    span_count: int,
) -> float | None:
    """구조화 confidence, evidence_span, 클러스터 coverage를 함께 반영한다."""

    base = _avg(values)
    if base is None:
        return None
    coverage = min(1.0, covered_count / max(total_count, 1))
    span_bonus = 1.0 if span_count > 0 else 0.0
    return round((0.70 * base) + (0.20 * coverage) + (0.10 * span_bonus), 4)


def _confidence_metrics(aspects: list[dict], requests: list[dict]) -> dict[str, float | int]:
    """aspect/request confidence와 evidence_span 현황을 metric으로 승격한다."""

    aspect_confidences = [float(item["confidence"]) for item in aspects if item.get("confidence") is not None]
    request_confidences = [float(item["confidence"]) for item in requests if item.get("confidence") is not None]
    metrics: dict[str, float | int] = {
        "aspect_evidence_span_count": sum(len(item.get("evidence_spans") or []) for item in aspects),
        "request_evidence_span_count": sum(len(item.get("evidence_spans") or []) for item in requests),
    }
    avg_aspect = _avg(aspect_confidences)
    avg_request = _avg(request_confidences)
    if avg_aspect is not None:
        metrics["avg_aspect_confidence"] = avg_aspect
    if avg_request is not None:
        metrics["avg_request_confidence"] = avg_request
    return metrics


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
