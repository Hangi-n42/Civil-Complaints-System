"""Complaint Intelligence Layer API 라우터."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.error_utils import error_response, make_request_id, now_iso
from app.complaint_intelligence import get_complaint_intelligence_service
from app.complaint_intelligence.duplicate_merger.service import DuplicateGroupNotFound, DuplicateMergeConflict
from app.complaint_intelligence.duplicate_merger.schemas import (
    DraftReplyPayload,
    DuplicateMergeRecord,
    DuplicateMergeStatus,
)
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.schemas import (
    ComplaintIntelligenceEvent,
    IssueAlert,
    PublicAgencyInsight,
    PublicInsightType,
)
from app.core.logging import api_logger


router = APIRouter(prefix="/complaint-intelligence", tags=["complaint-intelligence"])


class RunAnalysisRequest(BaseModel):
    """민원 지능화 분석 실행 요청."""

    request_id: Optional[str] = None
    events: list[ComplaintIntelligenceEvent] = Field(default_factory=list)


class RunAnalysisData(BaseModel):
    """민원 지능화 분석 실행 응답 데이터."""

    event_count: int
    alert_count: int
    public_insight_count: int
    alerts: list[IssueAlert]
    public_insights: list[PublicAgencyInsight]


class RunAnalysisResponse(BaseModel):
    """민원 지능화 분석 실행 응답."""

    success: bool = True
    request_id: str
    timestamp: str
    data: RunAnalysisData


class IssueAlertsData(BaseModel):
    """이슈 경보 목록 응답 데이터."""

    count: int
    alerts: list[IssueAlert]


class IssueAlertsResponse(BaseModel):
    """이슈 경보 목록 응답."""

    success: bool = True
    request_id: str
    timestamp: str
    data: IssueAlertsData


class PublicInsightsData(BaseModel):
    """공공기관 인사이트 목록 응답 데이터."""

    count: int
    public_insights: list[PublicAgencyInsight]


class PublicInsightsResponse(BaseModel):
    """공공기관 인사이트 목록 응답."""

    success: bool = True
    request_id: str
    timestamp: str
    data: PublicInsightsData


class DashboardSummary(BaseModel):
    """FE 대시보드 상단 지표."""

    alert_count: int
    critical_alert_count: int
    public_insight_count: int
    high_priority_insight_count: int
    human_review_required_count: int
    linked_alert_count: int


class DashboardIssueAlertCard(BaseModel):
    """FE 실시간 이슈 탭 카드."""

    id: str
    status: str
    severity: str
    severity_label: str
    color: str
    title: str
    summary: str
    topic: str
    region: Optional[str] = None
    center: Optional[dict[str, float]] = None
    radius: Optional[float] = None
    recent_count: int
    baseline: float
    surge_ratio: float
    confidence: float
    keywords: list[str]
    representative_complaint_ids: list[str]
    linked_insight_ids: list[str]
    map_focus: Optional[dict[str, Any]] = None
    first_seen: str
    last_seen: str


class DashboardActionItem(BaseModel):
    """FE 추천 조치 표시용 요약."""

    action: str
    horizon: str
    action_type: str
    responsible_unit_hint: Optional[str] = None
    why: str
    supporting_evidence_ids: list[str]
    expected_impact: Optional[str] = None
    risk_or_dependency: Optional[str] = None


class DashboardPublicInsightCard(BaseModel):
    """FE 행정 인사이트 탭 카드."""

    id: str
    type: PublicInsightType
    type_label: str
    status: str
    priority: str
    priority_label: str
    color: str
    title: str
    summary: str
    problem_diagnosis: str
    topic: str
    target_area: str
    affected_count: int
    affected_region: Optional[dict[str, Any]] = None
    related_department: Optional[str] = None
    window_start: str
    window_end: str
    confidence: float
    grounding_score: float
    requires_human_review: bool
    linked_alert_ids: list[str]
    representative_evidence_ids: list[str]
    top_aspects: list[dict[str, Any]]
    citizen_requests: list[dict[str, Any]]
    recommended_actions: list[DashboardActionItem]
    uncertainty: list[str]
    metrics: dict[str, float | int | str]


class DashboardData(BaseModel):
    """FE 민원 인텔리전스 탭 전체 데이터."""

    summary: DashboardSummary
    tabs: list[dict[str, str]]
    issue_alerts: list[DashboardIssueAlertCard]
    public_insights: list[DashboardPublicInsightCard]
    empty_state: dict[str, str]


class DashboardResponse(BaseModel):
    """FE 대시보드용 응답."""

    success: bool = True
    request_id: str
    timestamp: str
    data: DashboardData


class DuplicateGroupsData(BaseModel):
    """중복 병합 그룹 목록 응답 데이터."""

    event_count: Optional[int] = None
    count: int
    duplicate_groups: list[DuplicateMergeRecord]


class DuplicateGroupsResponse(BaseModel):
    """중복 병합 그룹 목록 응답."""

    success: bool = True
    request_id: str
    timestamp: str
    data: DuplicateGroupsData


class DuplicateGroupData(BaseModel):
    """중복 병합 그룹 단건 응답 데이터."""

    duplicate_group: DuplicateMergeRecord


class DuplicateGroupResponse(BaseModel):
    """중복 병합 그룹 단건 응답."""

    success: bool = True
    request_id: str
    timestamp: str
    data: DuplicateGroupData


class DuplicateDraftReplyData(BaseModel):
    """중복 병합 대표 답변 payload 응답 데이터."""

    draft_reply_payload: DraftReplyPayload


class DuplicateDraftReplyResponse(BaseModel):
    """중복 병합 대표 답변 payload 응답."""

    success: bool = True
    request_id: str
    timestamp: str
    data: DuplicateDraftReplyData


@router.post("/run-analysis", response_model=RunAnalysisResponse)
async def run_analysis(request: RunAnalysisRequest) -> RunAnalysisResponse:
    """민원 이벤트 배치를 분석해 경보와 공공기관 행정 인사이트를 생성한다."""

    request_id = request.request_id or make_request_id()
    service = get_complaint_intelligence_service()
    result = service.run_analysis(request.events)
    api_logger.info(
        "Complaint Intelligence analysis completed: request_id=%s events=%s alerts=%s public_insights=%s",
        request_id,
        len(request.events),
        len(result.alerts),
        len(result.public_insights),
    )
    return RunAnalysisResponse(
        request_id=request_id,
        timestamp=now_iso(),
        data=RunAnalysisData(
            event_count=len(request.events),
            alert_count=len(result.alerts),
            public_insight_count=len(result.public_insights),
            alerts=result.alerts,
            public_insights=result.public_insights,
        ),
    )


@router.post("/public-insights/run-analysis", response_model=RunAnalysisResponse)
async def run_public_insight_analysis(request: RunAnalysisRequest) -> RunAnalysisResponse:
    """공공기관 인사이트 분석을 명시적으로 실행한다."""

    return await run_analysis(request)


@router.post("/dashboard/run-analysis", response_model=DashboardResponse)
async def run_dashboard_analysis(request: RunAnalysisRequest) -> DashboardResponse:
    """분석 실행 후 FE 대시보드 카드 응답을 바로 반환한다."""

    request_id = request.request_id or make_request_id()
    service = get_complaint_intelligence_service()
    result = service.run_analysis(request.events)
    api_logger.info(
        "Complaint Intelligence dashboard analysis completed: request_id=%s events=%s alerts=%s public_insights=%s",
        request_id,
        len(request.events),
        len(result.alerts),
        len(result.public_insights),
    )
    return DashboardResponse(
        request_id=request_id,
        timestamp=now_iso(),
        data=_dashboard_data(result.alerts, result.public_insights),
    )


@router.get("/dashboard", response_model=DashboardResponse)
async def get_dashboard(
    status: Optional[str] = None,
    insight_type: Optional[PublicInsightType] = Query(default=None, alias="type"),
) -> DashboardResponse:
    """FE 민원 인텔리전스 탭에서 바로 사용할 카드형 데이터를 반환한다."""

    service = get_complaint_intelligence_service()
    alerts = service.list_issue_alerts(status=status)
    insights = service.list_public_insights(status=status, insight_type=insight_type)
    return DashboardResponse(
        request_id=make_request_id(),
        timestamp=now_iso(),
        data=_dashboard_data(alerts, insights),
    )


@router.post("/duplicate-groups/run-analysis", response_model=DuplicateGroupsResponse)
async def run_duplicate_group_analysis(request: RunAnalysisRequest) -> DuplicateGroupsResponse:
    """중복 민원 병합 후보 그룹 분석을 명시적으로 실행한다."""

    request_id = request.request_id or make_request_id()
    service = get_complaint_intelligence_service()
    groups = service.run_duplicate_analysis(request.events)
    api_logger.info(
        "Duplicate merge analysis completed: request_id=%s events=%s groups=%s",
        request_id,
        len(request.events),
        len(groups),
    )
    return DuplicateGroupsResponse(
        request_id=request_id,
        timestamp=now_iso(),
        data=DuplicateGroupsData(
            event_count=len(request.events),
            count=len(groups),
            duplicate_groups=groups,
        ),
    )


@router.get("/duplicate-groups", response_model=DuplicateGroupsResponse)
async def list_duplicate_groups(status: Optional[DuplicateMergeStatus] = None) -> DuplicateGroupsResponse:
    """저장된 중복 병합 추천 그룹을 조회한다."""

    groups = get_complaint_intelligence_service().list_duplicate_groups(status=status)
    return DuplicateGroupsResponse(
        request_id=make_request_id(),
        timestamp=now_iso(),
        data=DuplicateGroupsData(count=len(groups), duplicate_groups=groups),
    )


@router.get("/duplicate-groups/{merge_id}", response_model=DuplicateGroupResponse)
async def get_duplicate_group(merge_id: str) -> DuplicateGroupResponse:
    """중복 병합 추천 그룹 단건을 조회한다."""

    group = get_complaint_intelligence_service().get_duplicate_group(merge_id)
    if group is None:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    return DuplicateGroupResponse(
        request_id=make_request_id(),
        timestamp=now_iso(),
        data=DuplicateGroupData(duplicate_group=group),
    )


@router.post("/duplicate-groups/{merge_id}/confirm", response_model=DuplicateGroupResponse)
async def confirm_duplicate_group(merge_id: str) -> DuplicateGroupResponse | JSONResponse:
    """담당자 승인으로 candidate 그룹을 confirmed 상태로 전환한다."""

    try:
        group = get_complaint_intelligence_service().confirm_duplicate_group(merge_id)
    except DuplicateGroupNotFound:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    except DuplicateMergeConflict as exc:
        return _duplicate_conflict_response(exc)
    return DuplicateGroupResponse(
        request_id=make_request_id(),
        timestamp=now_iso(),
        data=DuplicateGroupData(duplicate_group=group),
    )


@router.post("/duplicate-groups/{merge_id}/split", response_model=DuplicateGroupResponse)
async def split_duplicate_group(merge_id: str) -> DuplicateGroupResponse | JSONResponse:
    """중복 병합 그룹을 split 상태로 전환한다."""

    try:
        group = get_complaint_intelligence_service().split_duplicate_group(merge_id)
    except DuplicateGroupNotFound:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    except DuplicateMergeConflict as exc:
        return _duplicate_conflict_response(exc)
    return DuplicateGroupResponse(
        request_id=make_request_id(),
        timestamp=now_iso(),
        data=DuplicateGroupData(duplicate_group=group),
    )


@router.post("/duplicate-groups/{merge_id}/reject", response_model=DuplicateGroupResponse)
async def reject_duplicate_group(merge_id: str) -> DuplicateGroupResponse | JSONResponse:
    """담당자 검토 결과 candidate 그룹을 rejected 상태로 전환한다."""

    try:
        group = get_complaint_intelligence_service().reject_duplicate_group(merge_id)
    except DuplicateGroupNotFound:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    except DuplicateMergeConflict as exc:
        return _duplicate_conflict_response(exc)
    return DuplicateGroupResponse(
        request_id=make_request_id(),
        timestamp=now_iso(),
        data=DuplicateGroupData(duplicate_group=group),
    )


@router.post("/duplicate-groups/{merge_id}/draft-reply", response_model=DuplicateDraftReplyResponse)
async def build_duplicate_draft_reply(merge_id: str) -> DuplicateDraftReplyResponse | JSONResponse:
    """confirmed 그룹에 대해서만 BE3 대표 답변 payload를 생성한다."""

    try:
        payload = get_complaint_intelligence_service().build_duplicate_draft_reply_payload(merge_id)
    except DuplicateGroupNotFound:
        raise HTTPException(status_code=404, detail="duplicate group not found")
    except DuplicateMergeConflict as exc:
        return _duplicate_conflict_response(exc)
    return DuplicateDraftReplyResponse(
        request_id=make_request_id(),
        timestamp=now_iso(),
        data=DuplicateDraftReplyData(draft_reply_payload=payload),
    )


@router.get("/issue-alerts", response_model=IssueAlertsResponse)
async def list_issue_alerts(status: Optional[str] = None) -> IssueAlertsResponse:
    """저장된 이슈 경보를 조회한다."""

    alerts = get_complaint_intelligence_service().list_issue_alerts(status=status)
    return IssueAlertsResponse(
        request_id=make_request_id(),
        timestamp=now_iso(),
        data=IssueAlertsData(count=len(alerts), alerts=alerts),
    )


@router.get("/public-insights", response_model=PublicInsightsResponse)
async def list_public_insights(
    status: Optional[str] = None,
    insight_type: Optional[PublicInsightType] = Query(default=None, alias="type"),
) -> PublicInsightsResponse:
    """저장된 공공기관 행정 인사이트를 조회한다."""

    insights = get_complaint_intelligence_service().list_public_insights(
        status=status,
        insight_type=insight_type,
    )
    return PublicInsightsResponse(
        request_id=make_request_id(),
        timestamp=now_iso(),
        data=PublicInsightsData(count=len(insights), public_insights=insights),
    )


@router.get("/public-insights/{insight_id}", response_model=PublicAgencyInsight)
async def get_public_insight(insight_id: str) -> PublicAgencyInsight:
    """저장된 공공기관 행정 인사이트를 ID로 조회한다."""

    insight = get_complaint_intelligence_service().get_public_insight(insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail="public insight not found")
    return insight


@router.get("/public-insights/{insight_id}/evidence-pack", response_model=PublicInsightEvidencePack)
async def get_public_insight_evidence_pack(insight_id: str) -> PublicInsightEvidencePack:
    """debug/admin 용도로 마스킹된 EvidencePack을 조회한다."""

    pack = get_complaint_intelligence_service().get_public_insight_evidence_pack(insight_id)
    if pack is None:
        raise HTTPException(status_code=404, detail="public insight evidence pack not found")
    return pack


def _dashboard_data(
    alerts: list[IssueAlert],
    insights: list[PublicAgencyInsight],
) -> DashboardData:
    """raw 분석 결과를 FE 카드형 read model로 변환한다."""

    return DashboardData(
        summary=DashboardSummary(
            alert_count=len(alerts),
            critical_alert_count=sum(1 for alert in alerts if alert.severity == "CRITICAL"),
            public_insight_count=len(insights),
            high_priority_insight_count=sum(1 for insight in insights if insight.priority in {"HIGH", "CRITICAL"}),
            human_review_required_count=sum(1 for insight in insights if insight.requires_human_review),
            linked_alert_count=sum(1 for insight in insights if insight.linked_alert_ids),
        ),
        tabs=[
            {"id": "issue_alerts", "label": "실시간 이슈"},
            {"id": "public_insights", "label": "행정 인사이트"},
        ],
        issue_alerts=[_alert_card(alert) for alert in alerts],
        public_insights=[_insight_card(insight) for insight in insights],
        empty_state={
            "issue_alerts": "현재 표시할 실시간 이슈가 없습니다.",
            "public_insights": "현재 표시할 행정 인사이트가 없습니다.",
        },
    )


def _alert_card(alert: IssueAlert) -> DashboardIssueAlertCard:
    """IssueAlert를 지도/경보 카드에 맞게 축약한다."""

    return DashboardIssueAlertCard(
        id=alert.id,
        status=alert.status,
        severity=alert.severity,
        severity_label=_severity_label(alert.severity),
        color=_severity_color(alert.severity),
        title=alert.title,
        summary=alert.summary,
        topic=alert.topic,
        region=alert.region,
        center=alert.center,
        radius=alert.radius,
        recent_count=alert.recent_count,
        baseline=alert.baseline,
        surge_ratio=alert.surge_ratio,
        confidence=alert.confidence,
        keywords=list(alert.keywords),
        representative_complaint_ids=[item.id for item in alert.representative_complaints],
        linked_insight_ids=list(alert.linked_insight_ids),
        map_focus=_map_focus(alert),
        first_seen=alert.first_seen.isoformat(),
        last_seen=alert.last_seen.isoformat(),
    )


def _insight_card(insight: PublicAgencyInsight) -> DashboardPublicInsightCard:
    """PublicAgencyInsight를 담당자 조치 브리핑 카드에 맞게 축약한다."""

    return DashboardPublicInsightCard(
        id=insight.insight_id,
        type=insight.type,
        type_label=_insight_type_label(str(insight.type)),
        status=insight.status,
        priority=insight.priority,
        priority_label=_priority_label(insight.priority),
        color=_priority_color(insight.priority),
        title=insight.title,
        summary=insight.summary,
        problem_diagnosis=insight.problem_diagnosis,
        topic=insight.topic,
        target_area=insight.target_area,
        affected_count=insight.affected_count,
        affected_region=insight.affected_region,
        related_department=insight.related_department,
        window_start=insight.window_start.isoformat(),
        window_end=insight.window_end.isoformat(),
        confidence=insight.confidence,
        grounding_score=insight.grounding_score,
        requires_human_review=insight.requires_human_review,
        linked_alert_ids=list(insight.linked_alert_ids),
        representative_evidence_ids=list(insight.representative_complaint_ids),
        top_aspects=[aspect.model_dump(mode="json") for aspect in insight.extracted_aspects[:3]],
        citizen_requests=[request.model_dump(mode="json") for request in insight.citizen_requests[:3]],
        recommended_actions=[
            DashboardActionItem(**action.model_dump(mode="json"))
            for action in insight.recommended_actions
        ],
        uncertainty=list(insight.uncertainty),
        metrics=dict(insight.metrics),
    )


def _duplicate_conflict_response(exc: DuplicateMergeConflict) -> JSONResponse:
    """중복 병합 상태 전이 충돌을 공통 에러 포맷으로 변환한다."""

    return error_response(
        request_id=make_request_id(),
        error_code=exc.code,
        message=exc.message,
        status_code=409,
        retryable=False,
        details=exc.details,
    )


def _map_focus(alert: IssueAlert) -> Optional[dict[str, Any]]:
    if not alert.center:
        return None
    return {
        "center": alert.center,
        "radius": alert.radius,
        "label": alert.region or alert.topic,
    }


def _severity_label(severity: str) -> str:
    return {"WATCH": "관찰", "WARNING": "주의", "CRITICAL": "긴급"}.get(severity, severity)


def _severity_color(severity: str) -> str:
    return {"WATCH": "gray", "WARNING": "amber", "CRITICAL": "red"}.get(severity, "gray")


def _priority_label(priority: str) -> str:
    return {"LOW": "낮음", "MEDIUM": "보통", "HIGH": "높음", "CRITICAL": "긴급"}.get(priority, priority)


def _priority_color(priority: str) -> str:
    return {"LOW": "gray", "MEDIUM": "blue", "HIGH": "amber", "CRITICAL": "red"}.get(priority, "gray")


def _insight_type_label(insight_type: str) -> str:
    labels = {
        "HOTSPOT_RESPONSE_REQUIRED": "핫스팟 대응",
        "SAFETY_RISK_SIGNAL": "안전 위험",
        "RECURRING_COMPLAINT_PATTERN": "반복 민원",
        "REGIONAL_SERVICE_GAP": "지역 서비스 격차",
        "DEPARTMENT_WORKLOAD_BOTTLENECK": "부서 업무 병목",
        "PROCESS_DELAY_RISK": "처리 지연",
        "REOPEN_OR_REPEAT_RISK": "재민원 위험",
        "SEASONAL_OR_TIME_PATTERN": "시간대/계절 패턴",
        "PUBLIC_GUIDANCE_NEEDED": "시민 안내 필요",
        "FACILITY_MAINTENANCE_PRIORITY": "시설 보수 우선순위",
        "ENFORCEMENT_PRIORITY": "단속 우선순위",
        "POLICY_IMPROVEMENT_OPPORTUNITY": "제도 개선 검토",
        "SERVICE_DESIGN_IMPROVEMENT": "서비스 설계 개선",
        "ACCESSIBILITY_OR_USABILITY_ISSUE": "접근성/사용성",
        "CITIZEN_COMMUNICATION_GAP": "시민 소통 격차",
    }
    return labels.get(insight_type, insight_type)
