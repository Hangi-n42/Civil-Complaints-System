"""SQLite 기반 Complaint Intelligence 영속 저장소."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from app.complaint_intelligence.duplicate_merger.schemas import DuplicateMergeRecord, DuplicateMergeStatus
from app.complaint_intelligence.pii import mask_strings as _mask_strings
from app.complaint_intelligence.public_insights.evidence_pack import PublicInsightEvidencePack
from app.complaint_intelligence.repository import (
    AnalysisRunMode,
    AnalysisRunRecord,
    AnalysisRunStatus,
    ComplaintIntelligenceRepository,
    CollectorCheckpointRecord,
    DashboardState,
)
from app.complaint_intelligence.schemas import ComplaintIntelligenceEvent, IssueAlert, PublicAgencyInsight


class SQLiteComplaintIntelligenceRepository(ComplaintIntelligenceRepository):
    """데모 환경에서 재시작 후에도 관제 상태를 유지하는 SQLite 저장소."""

    def __init__(self, db_path: str | Path, *, auto_create: bool = True) -> None:
        self.db_path = Path(db_path)
        self.auto_create = auto_create
        self._lock = RLock()
        if self.auto_create:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._initialize()

    def save_analysis_run(
        self,
        *,
        run_id: str,
        mode: AnalysisRunMode,
        source_name: str | None,
        event_count: int,
        started_at: datetime,
        as_of: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ci_analysis_runs (
                    run_id, mode, status, source_name, event_count,
                    started_at, completed_at, as_of, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    mode,
                    "running",
                    source_name,
                    event_count,
                    _dt(started_at),
                    None,
                    _dt(as_of),
                    _json(metadata or {}),
                ),
            )

    def complete_analysis_run(
        self,
        run_id: str,
        *,
        status: AnalysisRunStatus,
        completed_at: datetime,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT metadata_json FROM ci_analysis_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            current_metadata = _loads(row["metadata_json"]) if row else {}
            if metadata:
                current_metadata.update(metadata)
            connection.execute(
                """
                UPDATE ci_analysis_runs
                SET status = ?, completed_at = ?, metadata_json = ?
                WHERE run_id = ?
                """,
                (status, _dt(completed_at), _json(current_metadata), run_id),
            )

    def list_analysis_runs(self, *, limit: int = 20) -> list[AnalysisRunRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, mode, status, source_name, event_count,
                       started_at, completed_at, as_of, metadata_json
                FROM ci_analysis_runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (max(0, limit),),
            ).fetchall()
        return [
            AnalysisRunRecord(
                run_id=row["run_id"],
                mode=row["mode"],
                status=row["status"],
                source_name=row["source_name"],
                event_count=row["event_count"],
                started_at=_parse_dt(row["started_at"]),
                completed_at=_parse_dt(row["completed_at"]) if row["completed_at"] else None,
                as_of=_parse_dt(row["as_of"]),
                metadata=_loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def save_events(self, events: list[ComplaintIntelligenceEvent]) -> None:
        inserted_at = _dt(_now())
        rows = []
        for event in events:
            safe_event = ComplaintIntelligenceEvent.model_validate(event.model_dump(mode="json"))
            rows.append(
                (
                    safe_event.id,
                    _dt(safe_event.received_at),
                    safe_event.region,
                    safe_event.final_department,
                    safe_event.status,
                    _json_model(safe_event),
                    inserted_at,
                )
            )
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO ci_events (
                    event_id, received_at, region, final_department, status, payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_events(self, event_ids: list[str] | None = None) -> list[ComplaintIntelligenceEvent]:
        with self._lock, self._connect() as connection:
            if event_ids is None:
                rows = connection.execute(
                    "SELECT payload_json FROM ci_events ORDER BY received_at DESC"
                ).fetchall()
                return [_model(ComplaintIntelligenceEvent, row["payload_json"]) for row in rows]

            events: list[ComplaintIntelligenceEvent] = []
            for event_id in event_ids:
                row = connection.execute(
                    "SELECT payload_json FROM ci_events WHERE event_id = ?",
                    (event_id,),
                ).fetchone()
                if row:
                    events.append(_model(ComplaintIntelligenceEvent, row["payload_json"]))
            return events

    def save_issue_alerts(self, alerts: list[IssueAlert]) -> None:
        updated_at = _dt(_now())
        rows = [
            (
                alert.id,
                alert.status,
                alert.severity,
                alert.topic,
                alert.region,
                _dt(alert.first_seen),
                _dt(alert.last_seen),
                alert.confidence,
                _json_model(alert),
                updated_at,
            )
            for alert in alerts
        ]
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO ci_issue_alerts (
                    alert_id, status, severity, topic, region, first_seen,
                    last_seen, confidence, payload_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def list_issue_alerts(self, status: str | None = None) -> list[IssueAlert]:
        query = "SELECT payload_json FROM ci_issue_alerts"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status.upper())
        query += " ORDER BY confidence DESC, last_seen DESC"
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_model(IssueAlert, row["payload_json"]) for row in rows]

    def save_public_insights(self, insights: list[PublicAgencyInsight]) -> None:
        rows = [
            (
                insight.insight_id,
                insight.type,
                insight.status,
                insight.priority,
                insight.topic,
                insight.affected_count,
                insight.confidence,
                insight.grounding_score,
                _dt(insight.created_at),
                _dt(insight.updated_at) if insight.updated_at else None,
                _json_model(insight),
            )
            for insight in insights
        ]
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO ci_public_insights (
                    insight_id, type, status, priority, topic, affected_count,
                    confidence, grounding_score, created_at, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )

    def list_public_insights(
        self,
        *,
        status: str | None = None,
        insight_type: str | None = None,
    ) -> list[PublicAgencyInsight]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status.lower())
        if insight_type:
            clauses.append("type = ?")
            params.append(insight_type)
        query = "SELECT payload_json FROM ci_public_insights"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY confidence DESC, affected_count DESC"
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_model(PublicAgencyInsight, row["payload_json"]) for row in rows]

    def get_public_insight(self, insight_id: str) -> PublicAgencyInsight | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM ci_public_insights WHERE insight_id = ?",
                (insight_id,),
            ).fetchone()
        if not row:
            return None
        return _model(PublicAgencyInsight, row["payload_json"])

    def save_evidence_pack(self, insight_id: str, pack: PublicInsightEvidencePack) -> None:
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ci_evidence_packs (
                    insight_id, candidate_id, payload_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (insight_id, pack.candidate_id, _json_model(pack), _dt(_now())),
            )

    def get_evidence_pack(self, insight_id: str) -> PublicInsightEvidencePack | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM ci_evidence_packs WHERE insight_id = ?",
                (insight_id,),
            ).fetchone()
        if not row:
            return None
        return _model(PublicInsightEvidencePack, row["payload_json"])

    def save_duplicate_groups(self, groups: list[DuplicateMergeRecord]) -> None:
        rows = [
            (
                group.merge_id,
                group.status,
                group.confidence,
                _dt(group.updated_at),
                _json_model(group),
            )
            for group in groups
        ]
        with self._lock, self._connect() as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO ci_duplicate_groups (
                    merge_id, status, confidence, updated_at, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )

    def list_duplicate_groups(self, status: DuplicateMergeStatus | None = None) -> list[DuplicateMergeRecord]:
        query = "SELECT payload_json FROM ci_duplicate_groups"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY status != 'candidate', confidence DESC"
        with self._lock, self._connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_model(DuplicateMergeRecord, row["payload_json"]) for row in rows]

    def get_duplicate_group(self, merge_id: str) -> DuplicateMergeRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM ci_duplicate_groups WHERE merge_id = ?",
                (merge_id,),
            ).fetchone()
        if not row:
            return None
        return _model(DuplicateMergeRecord, row["payload_json"])

    def update_duplicate_group(self, group: DuplicateMergeRecord) -> None:
        self.save_duplicate_groups([group])

    def get_dashboard_state(self) -> DashboardState:
        with self._lock, self._connect() as connection:
            run = connection.execute(
                """
                SELECT run_id, mode, source_name, as_of
                FROM ci_analysis_runs
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
            event_state = connection.execute(
                "SELECT COUNT(*) AS event_count, MAX(received_at) AS latest_event_at FROM ci_events"
            ).fetchone()
            alert_state = connection.execute(
                "SELECT COUNT(*) AS active_count FROM ci_issue_alerts WHERE status IN ('ACTIVE', 'UPDATED')"
            ).fetchone()
            insight_state = connection.execute(
                "SELECT COUNT(*) AS high_count FROM ci_public_insights WHERE priority IN ('HIGH', 'CRITICAL')"
            ).fetchone()

        return DashboardState(
            as_of=_parse_dt(run["as_of"]) if run else None,
            latest_event_at=_parse_dt(event_state["latest_event_at"]) if event_state and event_state["latest_event_at"] else None,
            event_count=int(event_state["event_count"] or 0) if event_state else 0,
            active_alert_count=int(alert_state["active_count"] or 0) if alert_state else 0,
            high_priority_insight_count=int(insight_state["high_count"] or 0) if insight_state else 0,
            last_run_id=run["run_id"] if run else None,
            last_run_mode=run["mode"] if run else None,
            source_name=run["source_name"] if run else None,
        )

    def save_collector_checkpoint(self, checkpoint: CollectorCheckpointRecord) -> None:
        safe_metadata = _mask_strings(dict(checkpoint.metadata))
        with self._lock, self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ci_collector_checkpoints (
                    collector_name, source_name, mode, watermark,
                    last_event_count, updated_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.collector_name,
                    checkpoint.source_name,
                    checkpoint.mode,
                    _dt(checkpoint.watermark) if checkpoint.watermark else None,
                    checkpoint.last_event_count,
                    _dt(checkpoint.updated_at),
                    _json(safe_metadata),
                ),
            )

    def get_collector_checkpoint(
        self,
        collector_name: str,
        source_name: str,
    ) -> CollectorCheckpointRecord | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(
                """
                SELECT collector_name, source_name, mode, watermark,
                       last_event_count, updated_at, metadata_json
                FROM ci_collector_checkpoints
                WHERE collector_name = ? AND source_name = ?
                """,
                (collector_name, source_name),
            ).fetchone()
        if not row:
            return None
        return _checkpoint(row)

    def list_collector_checkpoints(self) -> list[CollectorCheckpointRecord]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                """
                SELECT collector_name, source_name, mode, watermark,
                       last_event_count, updated_at, metadata_json
                FROM ci_collector_checkpoints
                ORDER BY updated_at DESC
                """
            ).fetchall()
        return [_checkpoint(row) for row in rows]

    def clear(self) -> None:
        with self._lock, self._connect() as connection:
            for table in (
                "ci_analysis_runs",
                "ci_events",
                "ci_issue_alerts",
                "ci_public_insights",
                "ci_evidence_packs",
                "ci_duplicate_groups",
                "ci_collector_checkpoints",
            ):
                connection.execute(f"DELETE FROM {table}")

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS ci_analysis_runs (
                    run_id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_name TEXT NULL,
                    event_count INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NULL,
                    as_of TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ci_events (
                    event_id TEXT PRIMARY KEY,
                    received_at TEXT NOT NULL,
                    region TEXT NULL,
                    final_department TEXT NULL,
                    status TEXT NULL,
                    payload_json TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ci_issue_alerts (
                    alert_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    region TEXT NULL,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ci_public_insights (
                    insight_id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    affected_count INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    grounding_score REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ci_evidence_packs (
                    insight_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ci_duplicate_groups (
                    merge_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ci_collector_checkpoints (
                    collector_name TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    watermark TEXT NULL,
                    last_event_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    PRIMARY KEY (collector_name, source_name)
                );

                CREATE INDEX IF NOT EXISTS idx_ci_events_received_at ON ci_events(received_at);
                CREATE INDEX IF NOT EXISTS idx_ci_alerts_status ON ci_issue_alerts(status);
                CREATE INDEX IF NOT EXISTS idx_ci_insights_status_type ON ci_public_insights(status, type);
                CREATE INDEX IF NOT EXISTS idx_ci_duplicate_groups_status ON ci_duplicate_groups(status);
                CREATE INDEX IF NOT EXISTS idx_ci_collector_checkpoints_updated_at ON ci_collector_checkpoints(updated_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path))
        connection.row_factory = sqlite3.Row
        return connection


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_model(model: Any) -> str:
    return _json(_mask_strings(model.model_dump(mode="json")))


def _loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    payload = json.loads(value)
    return payload if isinstance(payload, dict) else {}


def _model(model_type: Any, payload_json: str) -> Any:
    return model_type.model_validate(json.loads(payload_json))


def _checkpoint(row: sqlite3.Row) -> CollectorCheckpointRecord:
    return CollectorCheckpointRecord(
        collector_name=row["collector_name"],
        source_name=row["source_name"],
        mode=row["mode"],
        watermark=_parse_dt(row["watermark"]) if row["watermark"] else None,
        last_event_count=int(row["last_event_count"] or 0),
        updated_at=_parse_dt(row["updated_at"]),
        metadata=_loads(row["metadata_json"]),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)
