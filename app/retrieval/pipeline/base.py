"""검색 평가 파이프라인의 기본 계약."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from app.evaluation.datasets import EvalQuery
from app.evaluation.metrics import RunRecord


@dataclass(frozen=True)
class RetrievedDoc:
    qid: str
    docid: str
    score: float
    rank: int
    stage: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_run_record(self) -> RunRecord:
        return RunRecord(
            qid=self.qid,
            docid=self.docid,
            score=self.score,
            rank=self.rank,
            stage=self.stage,
        )


@dataclass(frozen=True)
class StageInput:
    query: EvalQuery
    candidates: list[RetrievedDoc] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StageOutput:
    stage_name: str
    query: EvalQuery
    candidates: list[RetrievedDoc]
    latency_ms: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


class RetrievalStage(Protocol):
    name: str

    async def run(self, stage_input: StageInput) -> StageOutput:
        ...

