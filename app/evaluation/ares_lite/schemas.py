"""Schemas for the lightweight ARES-style RAG evaluator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _first_text(mapping: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(slots=True)
class AresLiteContext:
    context_id: str
    content: str
    source: str = ""
    rank: int = 0
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, item: dict[str, Any], *, index: int = 0) -> "AresLiteContext":
        content = _first_text(
            item,
            (
                "content",
                "text",
                "snippet",
                "quote",
                "page_content",
                "body",
                "answer",
            ),
        )
        title = _first_text(item, ("title", "case_title", "subject"))
        if title and title not in content:
            content = f"{title}\n{content}".strip()

        context_id = _first_text(
            item,
            (
                "context_id",
                "doc_id",
                "case_id",
                "source_id",
                "chunk_id",
                "id",
            ),
        ) or f"context-{index + 1}"
        source = _first_text(item, ("source", "source_type", "category", "origin"))
        rank = _to_int(item.get("rank"), index + 1)
        score = _to_float(item.get("score") or item.get("similarity") or item.get("rerank_score"))
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        return cls(
            context_id=context_id,
            content=content,
            source=source,
            rank=rank,
            score=score,
            metadata=dict(metadata),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_id": self.context_id,
            "content": self.content,
            "source": self.source,
            "rank": self.rank,
            "score": self.score,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class AresLiteCitation:
    doc_id: str
    quote: str = ""
    source: str = ""

    @classmethod
    def from_mapping(cls, item: dict[str, Any], *, index: int = 0) -> "AresLiteCitation":
        doc_id = _first_text(item, ("doc_id", "context_id", "case_id", "source_id", "id")) or f"citation-{index + 1}"
        quote = _first_text(item, ("quote", "snippet", "span", "text", "content"))
        source = _first_text(item, ("source", "source_type", "origin"))
        return cls(doc_id=doc_id, quote=quote, source=source)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "quote": self.quote,
            "source": self.source,
        }


@dataclass(slots=True)
class AresLiteCase:
    case_id: str
    query: str
    generated_answer: str
    retrieved_contexts: list[AresLiteContext] = field(default_factory=list)
    citations: list[AresLiteCitation] = field(default_factory=list)
    request_segments: list[str] = field(default_factory=list)
    routing_trace: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, item: dict[str, Any], *, index: int = 0) -> "AresLiteCase":
        case_id = _first_text(
            item,
            ("case_id", "complaint_id", "source_id", "id", "qid"),
        ) or f"case-{index + 1}"
        query = _first_text(
            item,
            (
                "query",
                "complaint_text",
                "complaint",
                "question",
                "민원내용",
                "title",
            ),
        )
        generated_answer = _first_text(
            item,
            (
                "generated_answer",
                "answer",
                "parsed_answer_repaired",
                "parsed_answer",
                "parsed_answer_strict",
                "response",
            ),
        )

        raw_contexts = (
            item.get("retrieved_contexts")
            or item.get("contexts")
            or item.get("references")
            or item.get("search_results")
            or item.get("retrieval_context")
            or []
        )
        contexts = [
            AresLiteContext.from_mapping(context, index=context_index)
            for context_index, context in enumerate(raw_contexts)
            if isinstance(context, dict)
        ]

        raw_citations = item.get("citations") or item.get("response_citations") or []
        citations = [
            AresLiteCitation.from_mapping(citation, index=citation_index)
            for citation_index, citation in enumerate(raw_citations)
            if isinstance(citation, dict)
        ]

        routing_trace = item.get("routing_trace") if isinstance(item.get("routing_trace"), dict) else {}
        structured_output = (
            item.get("structured_output") if isinstance(item.get("structured_output"), dict) else {}
        )
        raw_segments = (
            item.get("request_segments")
            or structured_output.get("request_segments")
            or routing_trace.get("request_segments")
            or []
        )
        request_segments = [str(segment).strip() for segment in raw_segments if str(segment).strip()]

        return cls(
            case_id=case_id,
            query=query,
            generated_answer=generated_answer,
            retrieved_contexts=contexts,
            citations=citations,
            request_segments=request_segments,
            routing_trace=dict(routing_trace),
            metadata={key: value for key, value in item.items() if key not in {"retrieved_contexts", "contexts"}},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "query": self.query,
            "request_segments": self.request_segments,
            "retrieved_contexts": [context.to_dict() for context in self.retrieved_contexts],
            "generated_answer": self.generated_answer,
            "citations": [citation.to_dict() for citation in self.citations],
            "routing_trace": self.routing_trace,
            "metadata": self.metadata,
        }
