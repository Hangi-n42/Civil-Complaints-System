"""실제 데이터 기반 Complaint Intelligence 데모 replay seed 생성 스크립트.

FE 대시보드를 하드코딩하지 않고 실제 분석 파이프라인에 넣을 수 있는
ComplaintIntelligenceEvent seed JSON을 만든다.
"""

from __future__ import annotations

import argparse
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


TEXT_FIELDS = (
    "body",
    "text",
    "raw_text",
    "content",
    "question",
    "query",
    "title",
    "consulting_content",
    "answer",
    "민원내용",
    "제목",
    "상담내용",
)
ID_FIELDS = ("id", "complaint_id", "case_id", "source_id", "번호", "관리번호")
DATE_FIELDS = ("received_at", "created_at", "submitted_at", "date", "consulting_date", "작성일")
REGION_FIELDS = ("region", "area", "district", "address", "주소", "지역", "자치구")
DEPARTMENT_FIELDS = (
    "final_department",
    "department",
    "assignee",
    "consulting_category",
    "category",
    "담당부서",
    "부서",
)


@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    label: str
    keywords: tuple[str, ...]
    expected_alert: bool
    expected_insight_types: tuple[str, ...]
    region: str
    department: str
    status: str
    structured_request: str
    structured_context: str


@dataclass
class Candidate:
    source_file: str
    source_id: str
    text: str
    title: str | None
    region: str | None
    department: str | None
    original_received_at: str | None
    score: float
    keyword_hits: list[str]


SCENARIOS: tuple[ScenarioSpec, ...] = (
    ScenarioSpec(
        id="sinkhole_hotspot",
        label="도로 침하/싱크홀 급증",
        keywords=("싱크홀", "침하", "구멍", "포트홀", "아스팔트", "꺼짐", "내려앉", "도로"),
        expected_alert=True,
        expected_insight_types=("SAFETY_RISK_SIGNAL", "HOTSPOT_RESPONSE_REQUIRED", "FACILITY_MAINTENANCE_PRIORITY"),
        region="중구",
        department="도로관리과",
        status="open",
        structured_request="현장 점검과 임시 안전 조치, 보수 일정을 요청합니다.",
        structured_context="같은 지역에서 최근 3시간 안에 도로 침하 관련 신고가 집중되었습니다.",
    ),
    ScenarioSpec(
        id="illegal_parking_enforcement",
        label="불법주정차 특정 시간대 반복",
        keywords=("불법주정차", "불법주차", "주정차", "주차", "단속", "차량", "어린이보호구역"),
        expected_alert=True,
        expected_insight_types=("ENFORCEMENT_PRIORITY", "HOTSPOT_RESPONSE_REQUIRED"),
        region="서구",
        department="교통지도과",
        status="open",
        structured_request="반복 시간대 단속 강화와 현장 안내 표지 보강을 요청합니다.",
        structured_context="출퇴근 또는 등하교 시간대에 같은 위치 민원이 반복됩니다.",
    ),
    ScenarioSpec(
        id="bulky_waste_guidance",
        label="대형폐기물 배출 방법 문의 반복",
        keywords=("대형폐기물", "폐기물", "스티커", "배출", "수거", "신청", "신고"),
        expected_alert=True,
        expected_insight_types=("PUBLIC_GUIDANCE_NEEDED", "SERVICE_DESIGN_IMPROVEMENT"),
        region="동구",
        department="청소행정과",
        status="open",
        structured_request="배출 신청 방법, 스티커 구매, 수거 기준 안내 보강을 요청합니다.",
        structured_context="대형폐기물 배출 절차를 확인하려는 문의가 최근 유입되었습니다.",
    ),
    ScenarioSpec(
        id="welfare_support_process",
        label="복지 지원 기준/신청 절차 불편 반복",
        keywords=("복지", "지원", "기준", "신청", "서류", "자격", "대상", "절차", "완화"),
        expected_alert=True,
        expected_insight_types=("POLICY_IMPROVEMENT_OPPORTUNITY", "PUBLIC_GUIDANCE_NEEDED"),
        region="중구",
        department="복지정책과",
        status="open",
        structured_request="지원 기준과 신청 절차, 필요 서류 안내를 쉽게 개선해 달라는 요청입니다.",
        structured_context="복지 지원 신청 전 단계에서 기준과 절차 이해 어려움이 반복됩니다.",
    ),
    ScenarioSpec(
        id="odor_night_hotspot",
        label="악취/냄새/하수 민원 야간 집중",
        keywords=("악취", "냄새", "하수", "오수", "쓰레기", "소음", "공장", "산책로"),
        expected_alert=True,
        expected_insight_types=("HOTSPOT_RESPONSE_REQUIRED", "SEASONAL_OR_TIME_PATTERN", "ENFORCEMENT_PRIORITY"),
        region="남구",
        department="환경관리과",
        status="open",
        structured_request="야간 시간대 현장 확인과 원인 점검, 시민 안내를 요청합니다.",
        structured_context="야간 또는 이른 오전 시간대에 악취·하수 관련 민원이 집중됩니다.",
    ),
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Complaint Intelligence demo replay seed from real data.")
    parser.add_argument("--input", action="append", default=None, help="입력 파일 또는 디렉터리. 여러 번 지정 가능.")
    parser.add_argument("--output", default="data/demo/complaint_intelligence_demo_events.json")
    parser.add_argument("--report", default="reports/complaint_intelligence_demo_seed_build_report.json")
    parser.add_argument("--as-of", default="2026-06-20T09:00:00+09:00")
    parser.add_argument("--source-name", default="complaint_intelligence_demo")
    parser.add_argument(
        "--description",
        default="실제 공개 민원 데이터를 실시간 관제 데모용 replay timeline으로 재배치한 seed",
    )
    parser.add_argument("--min-events-per-scenario", type=int, default=5)
    parser.add_argument("--max-events-per-scenario", type=int, default=6)
    parser.add_argument("--allow-synthetic-fill", default="false")
    args = parser.parse_args()

    input_paths = [Path(item) for item in (args.input or ["data/processed", "scripts/data"])]
    allow_synthetic_fill = str(args.allow_synthetic_fill).lower() == "true"
    seed, report = build_demo_seed(
        input_paths=input_paths,
        as_of=datetime.fromisoformat(args.as_of),
        min_events_per_scenario=args.min_events_per_scenario,
        max_events_per_scenario=args.max_events_per_scenario,
        allow_synthetic_fill=allow_synthetic_fill,
        source_name=args.source_name,
        description=args.description,
    )
    output_path = Path(args.output)
    report_path = Path(args.report)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output_path), "report": str(report_path), "scenario_count": len(seed["scenarios"])}, ensure_ascii=False, indent=2))
    return 0


def build_demo_seed(
    *,
    input_paths: list[Path],
    as_of: datetime,
    min_events_per_scenario: int,
    max_events_per_scenario: int,
    allow_synthetic_fill: bool,
    source_name: str = "complaint_intelligence_demo",
    description: str = "실제 공개 민원 데이터를 실시간 관제 데모용 replay timeline으로 재배치한 seed",
) -> tuple[dict[str, Any], dict[str, Any]]:
    records = list(iter_source_records(input_paths))
    scenarios: list[dict[str, Any]] = []
    scenario_reports: list[dict[str, Any]] = []

    for scenario_index, spec in enumerate(SCENARIOS):
        candidates = select_candidates(records, spec)
        selected = candidates[:max_events_per_scenario]
        synthetic_records: list[Candidate] = []
        if len(selected) < min_events_per_scenario and allow_synthetic_fill:
            synthetic_records = synthetic_candidates(spec, min_events_per_scenario - len(selected))
            selected.extend(synthetic_records)

        events = [
            build_event(
                spec=spec,
                candidate=candidate,
                event_index=index,
                scenario_index=scenario_index,
                as_of=as_of,
            )
            for index, candidate in enumerate(selected)
        ]
        validate_events(events)
        source_policy = source_policy_for(selected, synthetic_records)
        scenarios.append(
            {
                "id": spec.id,
                "label": spec.label,
                "expected_alert": spec.expected_alert,
                "expected_insight_types": list(spec.expected_insight_types),
                "expected_min_alerts": 1 if spec.expected_alert else 0,
                "expected_min_insights": 1,
                "source_policy": source_policy,
                "events": events,
                "source_records": [
                    source_record(candidate)
                    for candidate in selected
                    if not candidate.source_id.startswith("synthetic-")
                ],
            }
        )
        scenario_reports.append(
            {
                "scenario": spec.id,
                "label": spec.label,
                "source_policy": source_policy,
                "candidate_count": len(candidates),
                "selected_event_count": len(events),
                "real_event_count": len([item for item in selected if not item.source_id.startswith("synthetic-")]),
                "synthetic_event_count": len(synthetic_records),
                "passed_minimum": len(events) >= min_events_per_scenario,
                "source_ids": [candidate.source_id for candidate in selected if not candidate.source_id.startswith("synthetic-")],
            }
        )

    seed = {
        "mode": "replay",
        "source_name": source_name,
        "as_of": as_of.isoformat(),
        "description": description,
        "synthetic_fill_enabled": allow_synthetic_fill,
        "scenarios": scenarios,
    }
    report = {
        "as_of": as_of.isoformat(),
        "source_name": source_name,
        "description": description,
        "input_paths": [str(path) for path in input_paths],
        "source_record_count": len(records),
        "allow_synthetic_fill": allow_synthetic_fill,
        "min_events_per_scenario": min_events_per_scenario,
        "max_events_per_scenario": max_events_per_scenario,
        "scenarios": scenario_reports,
    }
    return seed, report


def iter_source_records(input_paths: list[Path]) -> Iterable[dict[str, Any]]:
    for root in input_paths:
        if root.is_file():
            files = [root]
        elif root.is_dir():
            files = sorted(path for path in root.rglob("*") if path.suffix.lower() in {".json", ".jsonl"})
        else:
            continue
        for path in files:
            yield from records_from_file(path)


def records_from_file(path: Path) -> Iterable[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        for line in read_text(path).splitlines():
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield from walk_json_records(payload, path)
        return

    try:
        payload = json.loads(read_text(path))
    except json.JSONDecodeError:
        return
    yield from walk_json_records(payload, path)


def walk_json_records(value: Any, path: Path) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            yield from walk_json_records(item, path)
        return
    if not isinstance(value, dict):
        return

    if extract_text(value):
        record = dict(value)
        record["_source_file"] = relative_source_path(path)
        yield record
    for nested in value.values():
        if isinstance(nested, (list, dict)):
            yield from walk_json_records(nested, path)


def read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def relative_source_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def select_candidates(records: list[dict[str, Any]], spec: ScenarioSpec) -> list[Candidate]:
    candidates: list[Candidate] = []
    seen_texts: set[str] = set()
    for record in records:
        raw_text = extract_text(record)
        if not raw_text:
            continue
        hits = [keyword for keyword in spec.keywords if keyword in raw_text]
        if not hits:
            continue
        masked_text = mask_pii(excerpt(raw_text, hits)).text
        normalized = " ".join(masked_text.split())
        if len(normalized) < 18 or normalized in seen_texts:
            continue
        seen_texts.add(normalized)
        candidates.append(
            Candidate(
                source_file=str(record.get("_source_file") or ""),
                source_id=extract_first(record, ID_FIELDS) or f"source-{len(candidates) + 1}",
                text=masked_text,
                title=mask_pii(str(record.get("title") or record.get("제목") or "")).text or None,
                region=extract_first(record, REGION_FIELDS),
                department=extract_first(record, DEPARTMENT_FIELDS),
                original_received_at=extract_first(record, DATE_FIELDS),
                score=score_candidate(raw_text, hits, record),
                keyword_hits=hits,
            )
        )
    return sorted(candidates, key=lambda item: item.score, reverse=True)


def score_candidate(text: str, hits: list[str], record: dict[str, Any]) -> float:
    length = len(text)
    length_score = 1.0 if 80 <= length <= 900 else 0.6
    region_score = 0.2 if extract_first(record, REGION_FIELDS) else 0.0
    department_score = 0.2 if extract_first(record, DEPARTMENT_FIELDS) else 0.0
    return round(len(set(hits)) * 2.0 + length_score + region_score + department_score, 4)


def extract_text(record: dict[str, Any]) -> str:
    chunks: list[str] = []
    for field in TEXT_FIELDS:
        value = record.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            chunks.append(value)
        elif isinstance(value, (int, float)):
            chunks.append(str(value))
    return "\n".join(chunk.strip() for chunk in chunks if chunk.strip())


def extract_first(record: dict[str, Any], fields: tuple[str, ...]) -> str | None:
    for field in fields:
        value = record.get(field)
        if value is None:
            continue
        if isinstance(value, (str, int, float)):
            cleaned = " ".join(str(value).split())
            if cleaned:
                return mask_pii(cleaned).text
    return None


def excerpt(text: str, hits: list[str], max_chars: int = 420) -> str:
    index = min((text.find(hit) for hit in hits if text.find(hit) >= 0), default=0)
    start = max(0, index - 120)
    end = min(len(text), start + max_chars)
    return " ".join(text[start:end].split())


def build_event(
    *,
    spec: ScenarioSpec,
    candidate: Candidate,
    event_index: int,
    scenario_index: int,
    as_of: datetime,
) -> dict[str, Any]:
    received_at = replay_time(as_of, scenario_index, event_index)
    body = candidate.text
    title = candidate.title or spec.label
    event = {
        "id": f"demo-{spec.id}-{event_index + 1:03d}",
        "received_at": received_at.isoformat(),
        "title": title[:120],
        "body": body,
        "region": scenario_region(spec, candidate),
        "final_department": candidate.department or spec.department,
        "status": spec.status,
        "civil_category": spec.label,
        "structured_elements": {
            "observation": {"text": body[:220], "confidence": 0.72},
            "result": {"text": f"{spec.label} 관련 불편과 행정 대응 필요성이 확인됩니다.", "confidence": 0.68},
            "request": {"text": spec.structured_request, "confidence": 0.74},
            "context": {"text": spec.structured_context, "confidence": 0.7},
        },
    }
    return ComplaintIntelligenceEvent.model_validate(event).model_dump(mode="json")


def replay_time(as_of: datetime, scenario_index: int, event_index: int) -> datetime:
    # 모든 시나리오가 최근 3시간 안에 들어오되 서로 약간씩 어긋나도록 배치한다.
    minutes_before = 10 + scenario_index * 7 + event_index * 9
    return as_of - timedelta(minutes=minutes_before)


def scenario_region(spec: ScenarioSpec, candidate: Candidate) -> str:
    if candidate.region and len(candidate.region) <= 20:
        return candidate.region
    return spec.region


def source_policy_for(selected: list[Candidate], synthetic_records: list[Candidate]) -> str:
    if synthetic_records and len(synthetic_records) == len(selected):
        return "synthetic_fill"
    if synthetic_records:
        return "real_text_excerpt_replayed_time_with_synthetic_fill"
    return "real_text_excerpt_replayed_time"


def source_record(candidate: Candidate) -> dict[str, Any]:
    return {
        "source_dataset": candidate.source_file,
        "source_id": candidate.source_id,
        "original_received_at": candidate.original_received_at,
        "original_region": candidate.region,
        "original_department": candidate.department,
        "keyword_hits": candidate.keyword_hits,
        "score": candidate.score,
        "masked_excerpt": candidate.text,
    }


def synthetic_candidates(spec: ScenarioSpec, count: int) -> list[Candidate]:
    candidates: list[Candidate] = []
    for index in range(count):
        text = (
            f"{spec.region}에서 {spec.label} 관련 민원이 반복 접수되었습니다. "
            f"{spec.structured_request}"
        )
        candidates.append(
            Candidate(
                source_file="synthetic_fill",
                source_id=f"synthetic-{spec.id}-{index + 1}",
                text=mask_pii(text).text,
                title=spec.label,
                region=spec.region,
                department=spec.department,
                original_received_at=None,
                score=0.0,
                keyword_hits=list(spec.keywords[:3]),
            )
        )
    return candidates


def validate_events(events: list[dict[str, Any]]) -> None:
    for event in events:
        ComplaintIntelligenceEvent.model_validate(event)


if __name__ == "__main__":
    raise SystemExit(main())
