from app.generation.context_mapper import map_retrieval_to_qa_context


def test_map_retrieval_to_qa_context_respects_chunk_and_char_budget() -> None:
    retrieval_results = [
        {
            "chunk_id": f"CASE-1__chunk-{i}",
            "case_id": "CASE-1",
            "doc_id": "DOC-1",
            "score": 0.9 - (i * 0.1),
            "snippet": "가" * 250,
        }
        for i in range(5)
    ]

    context, trace = map_retrieval_to_qa_context(
        retrieval_results=retrieval_results,
        top_k=5,
        policy={
            "model_ctx_tokens": 300,
            "reserved_output_tokens": 120,
            "reserved_system_tokens": 80,
            "chars_per_token": 2.0,
            "max_chunks": 3,
            "max_chars_per_chunk": 90,
        },
    )

    assert len(context) == 3
    assert trace["context_used_chars"] <= trace["context_budget_chars"]
    assert all(len(item["snippet"]) <= 90 for item in context)


def test_map_retrieval_to_qa_context_drops_invalid_items() -> None:
    retrieval_results = [
        {"chunk_id": "", "case_id": "CASE-1", "snippet": "유효하지 않음"},
        {"chunk_id": "CASE-1__chunk-1", "case_id": "", "snippet": "유효하지 않음"},
        {"chunk_id": "CASE-1__chunk-2", "case_id": "CASE-1", "snippet": "  "},
        {"chunk_id": "CASE-1__chunk-3", "case_id": "CASE-1", "snippet": "정상 스니펫"},
    ]

    context, trace = map_retrieval_to_qa_context(
        retrieval_results=retrieval_results,
        top_k=4,
        policy=None,
    )

    assert len(context) == 1
    assert context[0]["chunk_id"] == "CASE-1__chunk-3"
    assert trace["context_dropped_count"] >= 3


def test_map_retrieval_to_qa_context_preserves_priority_order() -> None:
    retrieval_results = [
        {
            "chunk_id": "CASE-1__chunk-9",
            "case_id": "CASE-1",
            "score": 0.99,
            "snippet": "첫 번째",
        },
        {
            "chunk_id": "CASE-1__chunk-2",
            "case_id": "CASE-1",
            "score": 0.75,
            "snippet": "두 번째",
        },
    ]

    context, _ = map_retrieval_to_qa_context(
        retrieval_results=retrieval_results,
        top_k=2,
        policy=None,
    )

    assert [item["chunk_id"] for item in context] == [
        "CASE-1__chunk-9",
        "CASE-1__chunk-2",
    ]
    assert context[0]["score"] == 0.99
