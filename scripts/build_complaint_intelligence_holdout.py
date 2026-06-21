"""실제 raw/processed 데이터에서 Complaint Intelligence holdout 50건을 만든다."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.complaint_intelligence.pii import mask_pii
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent


TEXT_KEYS = {
    "body",
    "text",
    "raw_text",
    "content",
    "question",
    "query",
    "title",
    "summary",
    "answer",
    "consulting_content",
    "description",
    "민원내용",
    "제목",
    "상담내용",
}
ID_KEYS = {"id", "complaint_id", "case_id", "source_id", "번호", "관리번호"}
DATE_KEYS = {"received_at", "created_at", "submitted_at", "date", "consulting_date", "작성일"}
REGION_KEYS = {"region", "area", "district", "address", "주소", "지역", "자치구"}
DEPARTMENT_KEYS = {"final_department", "department", "assignee", "consulting_category", "category", "담당부서", "부서"}


@dataclass(frozen=True)
class HoldoutBucket:
    id: str
    label: str
    target_count: int
    keywords: tuple[str, ...]
    region: str
    department: str
    request: str
    context: str
    status: str = "open"


@dataclass
class SourceCandidate:
    source_file: str
    source_id: str
    text: str
    title: str | None
    region: str | None
    department: str | None
    original_received_at: str | None
    keyword_hits: list[str]
    score: float


BUCKETS: tuple[HoldoutBucket, ...] = (
    HoldoutBucket(
        id="safety_facility",
        label="안전/시설",
        target_count=10,
        keywords=("도로", "침하", "싱크홀", "파손", "고장", "가로등", "침수", "하수", "공원", "놀이터"),
        region="중구",
        department="도로관리과",
        request="현장 점검과 보수 우선순위 검토를 요청합니다.",
        context="안전 또는 시설 유지보수 관련 실제 민원 holdout입니다.",
    ),
    HoldoutBucket(
        id="enforcement_order",
        label="단속/생활질서",
        target_count=10,
        keywords=("불법", "주정차", "주차", "단속", "무단투기", "쓰레기", "흡연", "현수막", "소음"),
        region="서구",
        department="교통지도과",
        request="반복 위치 단속과 시민 안내 보강을 요청합니다.",
        context="생활질서와 단속성 불편이 포함된 실제 민원 holdout입니다.",
    ),
    HoldoutBucket(
        id="guidance_process",
        label="안내/절차/서류",
        target_count=10,
        keywords=("신청", "서류", "절차", "방법", "기준", "자격", "안내", "문의", "허가", "지원"),
        region="동구",
        department="민원여권과",
        request="신청 기준과 절차 안내를 더 명확히 제공해 달라고 요청합니다.",
        context="행정 안내와 제출 서류 이해 어려움이 포함된 실제 민원 holdout입니다.",
    ),
    HoldoutBucket(
        id="service_accessibility",
        label="서비스/앱/접근성",
        target_count=8,
        keywords=("앱", "예약", "로그인", "결제", "대여", "접근성", "장애인", "고령자", "외국인", "불편"),
        region="남구",
        department="스마트도시과",
        request="서비스 이용 절차와 안내 흐름 개선을 요청합니다.",
        context="디지털 서비스와 접근성 관련 실제 민원 holdout입니다.",
    ),
    HoldoutBucket(
        id="delay_repeat_communication",
        label="처리 지연/재민원/소통",
        target_count=7,
        keywords=("지연", "처리", "답변", "재민원", "반복", "불만", "연락", "진행", "완료", "확인"),
        region="북구",
        department="감사담당관",
        request="처리 진행 상황과 완료 안내를 명확히 해 달라고 요청합니다.",
        context="처리 지연, 재문의, 소통 부족 관련 실제 민원 holdout입니다.",
        status="pending",
    ),
    HoldoutBucket(
        id="mixed_negative",
        label="기타/혼합/negative",
        target_count=5,
        keywords=(),
        region="광역시",
        department="민원콜센터",
        request="민원 내용을 검토하고 필요한 담당 부서 안내를 요청합니다.",
        context="특정 주제로 쉽게 묶이지 않는 실제 민원 holdout입니다.",
        status="open",
    ),
)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Build open-world Complaint Intelligence holdout set.")
    parser.add_argument("--input", action="append", default=None)
    parser.add_argument("--output", default="data/evaluation/complaint_intelligence_holdout_50.json")
    parser.add_argument("--report", default="reports/complaint_intelligence_holdout_build_report.json")
    parser.add_argument("--as-of", default="2026-06-20T09:00:00+09:00")
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()

    input_paths = [Path(item) for item in (args.input or ["data/processed", "scripts/data"])]
    holdout, report = build_holdout(input_paths=input_paths, as_of=datetime.fromisoformat(args.as_of), count=args.count)
    output_path = Path(args.output)
    report_path = Path(args.report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(holdout, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "report": str(report_path), "total_selected": report["total_selected"]}, ensure_ascii=False, indent=2))
    return 0 if report["total_selected"] == args.count else 1


def build_holdout(*, input_paths: list[Path], as_of: datetime, count: int) -> tuple[dict[str, Any], dict[str, Any]]:
    records = list(iter_source_candidates(input_paths))
    selected: list[tuple[HoldoutBucket, SourceCandidate]] = []
    used_hashes: set[str] = set()
    bucket_reports: list[dict[str, Any]] = []

    for bucket in BUCKETS:
        bucket_candidates = sorted(
            (candidate for candidate in records if candidate_matches_bucket(candidate, bucket)),
            key=lambda item: item.score,
            reverse=True,
        )
        picked = pick_unique(bucket_candidates, bucket.target_count, used_hashes)
        selected.extend((bucket, candidate) for candidate in picked)
        bucket_reports.append(
            {
                "bucket": bucket.id,
                "label": bucket.label,
                "target_count": bucket.target_count,
                "selected_count": len(picked),
                "source_files": sorted({candidate.source_file for candidate in picked}),
            }
        )

    if len(selected) < count:
        fallback_candidates = sorted(records, key=lambda item: item.score, reverse=True)
        mixed_bucket = next(bucket for bucket in BUCKETS if bucket.id == "mixed_negative")
        for candidate in pick_unique(fallback_candidates, count - len(selected), used_hashes):
            selected.append((mixed_bucket, candidate))

    selected = selected[:count]
    events = [
        build_event(bucket=bucket, candidate=candidate, index=index, as_of=as_of)
        for index, (bucket, candidate) in enumerate(selected)
    ]
    validate_events(events)

    category_distribution: dict[str, int] = {}
    for bucket, _candidate in selected:
        category_distribution[bucket.id] = category_distribution.get(bucket.id, 0) + 1

    holdout = {
        "mode": "replay",
        "source_name": "complaint_intelligence_holdout_50",
        "as_of": as_of.isoformat(),
        "description": "실제 raw/processed 민원 데이터를 PII 마스킹 후 open-world holdout으로 재배치한 평가셋",
        "evaluation_type": "open_world_holdout",
        "events": events,
    }
    report = {
        "total_selected": len(events),
        "real_text_count": len(events),
        "synthetic_count": 0,
        "source_files": sorted({candidate.source_file for _bucket, candidate in selected}),
        "category_distribution": category_distribution,
        "bucket_reports": bucket_reports,
        "pii_masking_applied": True,
        "sampling_notes": [
            "body와 masked_text에는 mask_pii 결과만 저장했습니다.",
            "지역/부서/received_at은 관제 replay 평가를 위해 bucket별로 보강했습니다.",
            "holdout은 정답 label 기반 성능 평가가 아니라 robustness/품질 점검용입니다.",
        ],
        "source_records": [
            {
                "holdout_id": event["id"],
                "bucket": bucket.id,
                "source_file": candidate.source_file,
                "source_id": candidate.source_id,
                "keyword_hits": candidate.keyword_hits[:10],
                "original_received_at": candidate.original_received_at,
            }
            for event, (bucket, candidate) in zip(events, selected)
        ],
    }
    return holdout, report


def iter_source_candidates(input_paths: list[Path]) -> Iterable[SourceCandidate]:
    seen: set[str] = set()
    for path in expand_input_paths(input_paths):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for item_index, item in enumerate(iter_dict_records(payload)):
            text = extract_text(item)
            if not text:
                continue
            masked = mask_pii(text).text
            normalized = " ".join(masked.split())
            if len(normalized) < 20:
                continue
            digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            keyword_hits = keyword_hits_for(normalized)
            yield SourceCandidate(
                source_file=str(path),
                source_id=extract_first(item, ID_KEYS) or f"{path.stem}-{item_index}",
                text=normalized[:900],
                title=extract_first(item, {"title", "제목"}),
                region=extract_first(item, REGION_KEYS),
                department=extract_first(item, DEPARTMENT_KEYS),
                original_received_at=extract_first(item, DATE_KEYS),
                keyword_hits=keyword_hits,
                score=score_candidate(normalized, keyword_hits),
            )


def expand_input_paths(input_paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in input_paths:
        if path.is_file() and path.suffix.lower() == ".json":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.json")))
    return files


def iter_dict_records(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from iter_dict_records(item)
    elif isinstance(value, dict):
        if any(key in value for key in TEXT_KEYS | ID_KEYS):
            yield value
        for item in value.values():
            if isinstance(item, (list, dict)):
                yield from iter_dict_records(item)


def extract_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in TEXT_KEYS:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    if not parts:
        for value in item.values():
            if isinstance(value, str) and 20 <= len(value.strip()) <= 1000:
                parts.append(value.strip())
    return " ".join(parts[:3]).strip()


def extract_first(item: dict[str, Any], keys: set[str]) -> str | None:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return mask_pii(text).text
    return None


def keyword_hits_for(text: str) -> list[str]:
    hits: list[str] = []
    for bucket in BUCKETS:
        for keyword in bucket.keywords:
            if keyword and keyword in text and keyword not in hits:
                hits.append(keyword)
    return hits


def score_candidate(text: str, hits: list[str]) -> float:
    length_score = 1.0 if 40 <= len(text) <= 450 else 0.5
    return len(hits) * 2.0 + length_score


def candidate_matches_bucket(candidate: SourceCandidate, bucket: HoldoutBucket) -> bool:
    if not bucket.keywords:
        return True
    return any(keyword in candidate.text for keyword in bucket.keywords)


def pick_unique(candidates: list[SourceCandidate], count: int, used_hashes: set[str]) -> list[SourceCandidate]:
    picked: list[SourceCandidate] = []
    for candidate in candidates:
        digest = hashlib.sha1(candidate.text.encode("utf-8")).hexdigest()
        if digest in used_hashes:
            continue
        used_hashes.add(digest)
        picked.append(candidate)
        if len(picked) >= count:
            break
    return picked


def build_event(*, bucket: HoldoutBucket, candidate: SourceCandidate, index: int, as_of: datetime) -> dict[str, Any]:
    received_at = as_of - timedelta(minutes=5 + (index % 10) * 9 + (index // 10) * 3)
    event_id = f"holdout-{bucket.id}-{index + 1:03d}"
    masked_text = mask_pii(candidate.text).text
    return {
        "id": event_id,
        "received_at": received_at.isoformat(),
        "title": mask_pii(candidate.title or masked_text[:80]).text,
        "body": masked_text,
        "masked_text": masked_text,
        "region": candidate.region or bucket.region,
        "final_department": candidate.department or bucket.department,
        "status": bucket.status,
        "handling_time_minutes": 1800 if bucket.id == "delay_repeat_communication" else None,
        "reopened": bucket.id == "delay_repeat_communication" and index % 3 == 0,
        "civil_category": bucket.label,
        "structured_elements": {
            "observation": {"text": masked_text[:300], "confidence": 0.65},
            "result": {"text": f"{bucket.label} 관련 시민 불편이 확인됩니다.", "confidence": 0.6},
            "request": {"text": bucket.request, "confidence": 0.62},
            "context": {"text": bucket.context, "confidence": 0.58},
        },
        "entity_texts": [candidate.region or bucket.region, bucket.label],
        "request_segments": [bucket.request],
        "pii_status": "MASKED",
        "pii_detected": False,
        "pii_labels": [],
    }


def validate_events(events: list[dict[str, Any]]) -> None:
    for event in events:
        model = ComplaintIntelligenceEvent.model_validate(event)
        serialized = model.model_dump_json()
        if mask_pii(serialized).detected_labels:
            raise ValueError(f"PII remained after validation: {event.get('id')}")


if __name__ == "__main__":
    raise SystemExit(main())
