"""Retrieval -> QA 컨텍스트 안전 매핑 유틸."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

DEFAULT_POLICY: Dict[str, Any] = {
    "model_ctx_tokens": 2048,
    "reserved_output_tokens": 512,
    "reserved_system_tokens": 256,
    "chars_per_token": 2.0,
    "max_chunks": 8,
    "max_chars_per_chunk": 320,
}

MIN_SNIPPET_CHARS = 40


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _clip_text(text: str, limit: int) -> Tuple[str, bool]:
    if limit <= 0:
        return "", bool(text)
    if len(text) <= limit:
        return text, False
    clipped = text[: max(0, limit - 3)].rstrip()
    return f"{clipped}...", True


def map_retrieval_to_qa_context(
    *,
    retrieval_results: List[Dict[str, Any]],
    top_k: int,
    policy: Dict[str, Any] | None,
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """검색 결과를 QA 모델 입력용 경량 컨텍스트로 매핑한다."""

    resolved = {**DEFAULT_POLICY, **(policy or {})}

    model_ctx_tokens = int(resolved["model_ctx_tokens"])
    reserved_output_tokens = int(resolved["reserved_output_tokens"])
    reserved_system_tokens = int(resolved["reserved_system_tokens"])
    chars_per_token = float(resolved["chars_per_token"])
    max_chunks = int(resolved["max_chunks"])
    max_chars_per_chunk = int(resolved["max_chars_per_chunk"])

    safe_ctx_tokens = max(1, model_ctx_tokens - reserved_output_tokens - reserved_system_tokens)
    context_budget_chars = max(MIN_SNIPPET_CHARS, int(safe_ctx_tokens * chars_per_token))
    target_chunks = max(1, min(max_chunks, max(1, int(top_k))))

    mapped: List[Dict[str, Any]] = []
    used_chars = 0
    truncated_count = 0
    dropped_count = 0

    for raw in retrieval_results:
        if len(mapped) >= target_chunks:
            break

        chunk_id = str(raw.get("chunk_id") or "").strip()
        case_id = str(raw.get("case_id") or "").strip()
        snippet = _normalize_text(raw.get("snippet"))

        if not chunk_id or not case_id or not snippet:
            dropped_count += 1
            continue

        remaining_slots = target_chunks - len(mapped)
        remaining_chars = context_budget_chars - used_chars
        reserve_for_next = MIN_SNIPPET_CHARS * max(0, remaining_slots - 1)
        allowed_chars = min(max_chars_per_chunk, max(MIN_SNIPPET_CHARS, remaining_chars - reserve_for_next))

        if remaining_chars < MIN_SNIPPET_CHARS:
            dropped_count += 1
            break

        clipped_snippet, truncated = _clip_text(snippet, allowed_chars)
        if not clipped_snippet:
            dropped_count += 1
            continue

        item: Dict[str, Any] = {
            "doc_id": raw.get("doc_id"),
            "chunk_id": chunk_id,
            "case_id": case_id,
            "snippet": clipped_snippet,
            "score": float(raw.get("score", raw.get("relevance_score", 0.0)) or 0.0),
        }
        mapped.append(item)
        used_chars += len(clipped_snippet)
        if truncated:
            truncated_count += 1

    consumed_inputs = len(mapped) + dropped_count
    dropped_count += max(0, len(retrieval_results) - consumed_inputs)

    trace = {
        "context_budget_chars": int(context_budget_chars),
        "context_used_chars": int(used_chars),
        "context_truncated_count": int(truncated_count),
        "context_dropped_count": int(dropped_count),
    }
    return mapped, trace
