"""민원 클러스터의 세부 불편 측면과 시민 요구를 추출한다."""

from __future__ import annotations

from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack


ASPECT_CATALOG: dict[str, list[str]] = {
    "신청 절차": ["신청", "절차", "복잡", "어려", "단계", "서류"],
    "지원 기준": ["지원", "기준", "자격", "대상", "조건", "완화", "확대"],
    "요금/비용": ["요금", "비용", "수수료", "비싸", "부담"],
    "안내 부족": ["안내", "모르", "어디", "어떻게", "필요서류", "문의"],
    "처리 지연": ["지연", "늦", "처리 안", "처리되지", "미처리", "답변 없음", "오래"],
    "재민원/반복 민원": ["재민원", "반복", "재문의", "재접수", "다시", "재발", "여러 번", "계속"],
    "처리 완료 후 재문의": ["처리 완료", "완료 안내", "완료 후", "재문의", "재점검", "다시 접수"],
    "처리 결과 불만": ["처리 결과", "불만", "만족도", "바뀌지", "해결되지", "재발", "조치 실효성"],
    "현장 안전": ["위험", "사고", "꺼짐", "침하", "붕괴", "감전", "침수", "싱크홀", "구멍", "움푹"],
    "시설 파손": ["파손", "고장", "꺼짐", "깨짐", "침하", "막힘", "구멍", "움푹", "내려앉", "아스팔트"],
    "단속 공백": ["불법", "단속", "주정차", "소음", "무단투기", "흡연", "현수막", "목줄"],
    "생활환경 불편": ["악취", "냄새", "소음", "진동", "담배", "쓰레기", "배설물"],
    "소음/진동": ["소음", "진동", "공사장", "작업 소음", "차량 소음", "생활 소음"],
    "시간대 집중": ["야간", "새벽", "주말", "퇴근", "이른 아침", "밤", "시간대", "등하교"],
    "침수 위험": ["침수", "집중호우", "빗물", "물고임", "범람", "저지대"],
    "배수 불량": ["배수", "맨홀", "우수관", "하수도", "빗물받이", "역류", "막힘"],
    "시설 막힘/역류": ["막힘", "역류", "맨홀", "하수구", "빗물받이", "우수관"],
    "무단투기": ["무단투기", "쓰레기", "폐기물", "불법 투기", "방치"],
    "쓰레기 적치": ["적치", "방치", "쌓여", "생활폐기물", "쓰레기 더미"],
    "청소 주기 부족": ["청소", "수거", "정기", "주기", "방치"],
    "이용 안전": ["안전", "위험", "다칠", "어린이", "놀이터", "산책로"],
    "유지보수 지연": ["보수", "수리", "정비", "지연", "고장", "파손"],
    "야간 이용 불안": ["야간", "밤", "어두", "불안", "위험"],
    "조명 고장": ["가로등", "보안등", "조명", "꺼짐", "점멸", "고장"],
    "야간 보행 불안": ["야간 보행", "밤길", "어두", "골목", "보행 안전"],
    "배차 간격": ["배차", "간격", "버스", "대기", "노선"],
    "정류장 접근성": ["정류장", "접근", "승강장", "환승", "보행"],
    "노선 안내 부족": ["노선", "배차 안내", "도착 안내", "정류장 안내", "안내 부족"],
    "방범 취약": ["방범", "CCTV", "순찰", "범죄", "취약"],
    "야간 안전 불안": ["야간 안전", "밤길", "불안", "사각지대", "방범"],
    "시설 설치 요청": ["설치", "CCTV", "표지", "조명", "안전시설"],
    "사각지대": ["사각지대", "보이지", "취약 구간", "감시"],
    "흡연 반복": ["흡연", "담배", "금연구역", "간접흡연", "담배꽁초"],
    "불법 광고물": ["불법 광고물", "현수막", "광고물", "불법 현수막"],
    "도시 미관 저해": ["미관", "지저분", "광고물", "현수막", "정비"],
    "보행/시야 방해": ["보행", "시야", "가림", "방해", "도로"],
    "반복 위치": ["같은 위치", "반복 위치", "계속 같은", "매번"],
    "반려동물 관리": ["반려동물", "목줄", "배설물", "유기동물", "개"],
    "배설물 방치": ["배설물", "방치", "치우지", "위생"],
    "목줄 미착용": ["목줄", "미착용", "풀어", "위험"],
    "생활 안전/위생": ["위생", "안전", "불쾌", "악취", "배설물"],
    "기준 이해 어려움": ["기준", "자격", "면허", "인허가", "이해하기 어렵"],
    "제출 서류": ["제출 서류", "필요서류", "서류", "증빙", "체크리스트"],
    "담당 부서 안내 부족": ["담당 부서", "어느 부서", "상담 경로", "연락처", "안내 부족"],
    "접근성/사용성": ["앱", "로그인", "예약", "결제", "불편", "어려움", "오류"],
    "취약계층 이용 불편": ["고령자", "장애인", "외국인", "취약계층", "휠체어", "외국어"],
    "신청/예약 절차 어려움": ["신청", "예약", "절차", "복잡", "본인 확인", "로그인"],
    "통학 안전": ["어린이보호구역", "통학", "등하교", "학교 앞", "어린이"],
    "등하교 시간 집중": ["등하교", "등교", "하교", "통학 시간", "아침", "오후"],
    "교통 위험": ["교통", "차량", "불법주정차", "속도", "위험"],
    "소통 부족": ["진행", "상태", "담당", "기간", "왜", "연락"],
}

REQUEST_CATALOG: dict[str, tuple[str, list[str]]] = {
    "정보 제공": ("정보 제공", ["안내", "문의", "어디", "어떻게", "필요서류", "기준", "공사 시간", "노선", "외국어"]),
    "절차 개선": ("절차 개선", ["절차", "복잡", "단계", "신청", "인허가", "예약"]),
    "현장 점검": ("현장 점검", ["위험", "점검", "침하", "꺼짐", "악취", "공사", "방범", "CCTV", "통학"]),
    "시설 보수": ("시설 보수", ["파손", "고장", "보수", "수리", "침하", "배수", "맨홀", "가로등", "놀이터"]),
    "단속 강화": ("단속 강화", ["단속", "불법", "주정차", "무단투기", "흡연", "현수막", "목줄", "공사 소음"]),
    "기준 완화": ("기준 완화", ["기준", "완화", "자격", "조건"]),
    "지원 확대": ("지원 확대", ["지원", "확대", "대상"]),
    "서비스 개선": ("서비스 개선", ["앱", "예약", "대여", "결제", "오류", "불편", "노선", "배차", "정류장"]),
    "처리 속도 개선": ("처리 속도 개선", ["지연", "늦", "오래", "처리 안", "재발 원인"]),
    "소통 강화": ("소통 강화", ["진행", "상태", "담당", "기간", "연락", "완료 안내", "처리 완료", "현장 조치 검증"]),
}


class AspectExtractor:
    """규칙 기반 aspect/request 추출기."""

    def enrich(self, pack: PublicInsightEvidencePack) -> PublicInsightEvidencePack:
        """EvidencePack에 aspect와 시민 요구를 근거 ID와 함께 채운다."""

        data = pack.model_copy(deep=True)
        data.extracted_aspects = _filter_aspects_for_pack(pack, self.extract_aspects(pack))
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
    has_structured_text = False
    for field in fields:
        payload = _structured_payload(complaint, field)
        text = str(payload.get("text") or "").strip()
        if text and not payload.get("operational_signal_only"):
            has_structured_text = True
        if text and any(keyword in text for keyword in keywords):
            return text, field, payload

    # 구조화 4요소가 이미 있으면 그 값을 우선 신뢰한다.
    # masked_text까지 다시 훑으면 "요청/안내/위험" 같은 넓은 단어가
    # unrelated aspect로 번지는 경우가 있어, 구조화 누락 시에만 fallback한다.
    if has_structured_text:
        return None

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


TOPIC_ASPECT_RUBRIC: tuple[tuple[tuple[str, ...], set[str]], ...] = (
    (("도로 침하", "싱크홀", "포트홀"), {"현장 안전", "시설 파손", "이용 안전", "유지보수 지연"}),
    (("복지", "지원 기준", "신청 절차"), {"신청 절차", "지원 기준", "안내 부족", "기준 이해 어려움", "제출 서류"}),
    (("공공자전거", "예약", "대여", "앱"), {"접근성/사용성", "신청/예약 절차 어려움", "신청 절차", "안내 부족", "기준 이해 어려움"}),
    (("대형폐기물", "배출"), {"신청 절차", "안내 부족", "기준 이해 어려움"}),
    (("불법주정차", "주정차", "학교 앞"), {"단속 공백", "시간대 집중", "통학 안전", "등하교 시간 집중", "교통 위험", "현장 안전"}),
    (("악취", "냄새", "하수"), {"생활환경 불편", "시간대 집중", "배수 불량", "시설 막힘/역류"}),
    (("처리 지연", "미처리", "부서 처리량"), {"처리 지연", "유지보수 지연", "소통 부족", "담당 부서 안내 부족"}),
    (("재민원", "반복 민원"), {"재민원/반복 민원", "처리 완료 후 재문의", "처리 결과 불만", "소통 부족", "생활환경 불편"}),
    (("공사 소음", "소음", "진동"), {"소음/진동", "시간대 집중", "단속 공백", "생활환경 불편"}),
    (("침수", "배수", "맨홀"), {"침수 위험", "배수 불량", "시설 막힘/역류", "현장 안전"}),
    (("무단투기", "쓰레기 적치"), {"무단투기", "쓰레기 적치", "청소 주기 부족", "안내 부족"}),
    (("공원", "놀이터", "산책로"), {"시설 파손", "이용 안전", "유지보수 지연", "야간 이용 불안"}),
    (("가로등", "보안등", "조명"), {"조명 고장", "야간 보행 불안", "현장 안전", "시설 파손"}),
    (("버스", "정류장", "노선", "배차"), {"배차 간격", "정류장 접근성", "노선 안내 부족", "접근성/사용성"}),
    (("CCTV", "방범", "사각지대"), {"방범 취약", "야간 안전 불안", "시설 설치 요청", "사각지대"}),
    (("금연", "흡연", "담배"), {"흡연 반복", "단속 공백", "안내 부족", "생활환경 불편"}),
    (("현수막", "광고물"), {"불법 광고물", "도시 미관 저해", "보행/시야 방해", "반복 위치"}),
    (("반려동물", "배설물", "목줄"), {"반려동물 관리", "배설물 방치", "목줄 미착용", "생활 안전/위생"}),
    (("인허가", "자격", "면허", "제출 서류"), {"기준 이해 어려움", "신청 절차", "제출 서류", "담당 부서 안내 부족", "안내 부족"}),
    (("접근성", "사용성", "고령자", "장애인", "외국인", "취약계층"), {"접근성/사용성", "안내 부족", "신청/예약 절차 어려움", "취약계층 이용 불편"}),
    (("어린이보호구역", "통학", "등하교"), {"통학 안전", "등하교 시간 집중", "교통 위험", "단속 공백", "현장 안전"}),
)

TYPE_ASPECT_RUBRIC: dict[str, set[str]] = {
    "SAFETY_RISK_SIGNAL": {
        "현장 안전",
        "시설 파손",
        "침수 위험",
        "배수 불량",
        "조명 고장",
        "야간 보행 불안",
        "통학 안전",
        "교통 위험",
        "방범 취약",
        "야간 안전 불안",
    },
    "HOTSPOT_RESPONSE_REQUIRED": {"현장 안전", "시설 파손", "시간대 집중", "생활환경 불편", "단속 공백"},
    "ENFORCEMENT_PRIORITY": {"단속 공백", "무단투기", "흡연 반복", "불법 광고물", "반려동물 관리", "시간대 집중"},
    "PUBLIC_GUIDANCE_NEEDED": {"안내 부족", "신청 절차", "기준 이해 어려움", "제출 서류", "담당 부서 안내 부족"},
    "SERVICE_DESIGN_IMPROVEMENT": {"접근성/사용성", "신청/예약 절차 어려움", "배차 간격", "정류장 접근성"},
    "ACCESSIBILITY_OR_USABILITY_ISSUE": {"접근성/사용성", "신청/예약 절차 어려움", "취약계층 이용 불편", "안내 부족"},
    "REOPEN_OR_REPEAT_RISK": {"재민원/반복 민원", "처리 완료 후 재문의", "처리 결과 불만", "소통 부족", "생활환경 불편"},
    "PROCESS_DELAY_RISK": {"처리 지연", "소통 부족", "담당 부서 안내 부족"},
    "DEPARTMENT_WORKLOAD_BOTTLENECK": {"처리 지연", "소통 부족", "담당 부서 안내 부족"},
}


def _filter_aspects_for_pack(pack: PublicInsightEvidencePack, aspects: list[dict]) -> list[dict]:
    """주제/유형과 무관한 넓은 키워드 aspect를 운영 노출 전에 줄인다."""

    allowed = _allowed_aspects_for_pack(pack)
    if not allowed:
        return aspects
    filtered = [aspect for aspect in aspects if str(aspect.get("aspect") or "") in allowed]
    return filtered or aspects


def _allowed_aspects_for_pack(pack: PublicInsightEvidencePack) -> set[str]:
    topic = str(pack.topic_label or "")
    compact_topic = topic.replace(" ", "")
    allowed: set[str] = set()
    for keywords, aspect_names in TOPIC_ASPECT_RUBRIC:
        if any(keyword.replace(" ", "") in compact_topic for keyword in keywords):
            allowed.update(aspect_names)
    allowed.update(TYPE_ASPECT_RUBRIC.get(str(pack.type_hint or ""), set()))
    return allowed


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
