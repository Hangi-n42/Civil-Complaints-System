"""Run QA generation directly from raw municipal consulting datasets.

This script supports datasets shaped like VS_지방행정기관/성남시_test_10.json where
records include consulting_content but do NOT include an explicit 'query' or 'context'.

Flow per record:
1) Derive query + routing trace from the record (PromptFactory)
2) Retrieve grounding chunks from local ChromaDB (/data/chroma_db)
3) Build RAG prompt and call Ollama
4) Parse the JSON response (relaxed) and persist results

Usage:
  python scripts/run_raw_dataset_qa.py \
    --input VS_지방행정기관/성남시_test_10.json \
    --output logs/evaluation/raw_dataset_qa_results.json \
    --limit 10 \
    --mode compact
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.logging import evaluation_logger
from app.core.exceptions import GenerationError, RetrievalError
from app.generation.service import get_generation_service


def _read_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("input JSON must be a list of records")
    return [row for row in payload if isinstance(row, dict)]


async def _run_one(
    *,
    generation_service,
    record: Dict[str, Any],
    mode: str,
    top_k: int | None,
    collection_name: str,
    temperature: float,
) -> Dict[str, Any]:
    prompt, context, derived_trace = await generation_service.build_rag_prompt_from_record_autoretrieve(
        record=record,
        routing_trace={},
        mode=mode,
        top_k=top_k,
        collection_name=collection_name,
    )

    raw_response = await generation_service.call_ollama(prompt, temperature=temperature)
    parsed = await generation_service.parse_json_response_relaxed(raw_response, context=context)

    return {
        "source_id": record.get("source_id"),
        "source": record.get("source"),
        "consulting_date": record.get("consulting_date"),
        "consulting_category": record.get("consulting_category"),
        "query": derived_trace.get("derived_query") if "derived_query" in derived_trace else None,
        "routing_trace": derived_trace,
        "context": context,
        "raw_response": raw_response,
        "parsed": parsed,
    }


async def run(args) -> int:
    logger = evaluation_logger
    generation_service = get_generation_service()

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records = _read_json(input_path)
    if args.limit and args.limit > 0:
        records = records[: args.limit]

    logger.info(
        "Raw dataset QA run: input=%s, records=%d, mode=%s, top_k=%s, collection=%s",
        str(input_path),
        len(records),
        args.mode,
        str(args.top_k),
        args.collection,
    )

    results: List[Dict[str, Any]] = []
    failures = 0

    for index, record in enumerate(records, start=1):
        try:
            results.append(
                await _run_one(
                    generation_service=generation_service,
                    record=record,
                    mode=args.mode,
                    top_k=args.top_k,
                    collection_name=args.collection,
                    temperature=args.temperature,
                )
            )
            logger.info("[%d/%d] ok", index, len(records))
        except (GenerationError, RetrievalError, ValueError) as e:
            failures += 1
            logger.warning("[%d/%d] failed: %s", index, len(records), str(e))
            results.append(
                {
                    "source_id": record.get("source_id"),
                    "error": str(e),
                    "record": record,
                }
            )
        except Exception as e:
            failures += 1
            logger.exception("[%d/%d] unexpected failure", index, len(records))
            results.append(
                {
                    "source_id": record.get("source_id"),
                    "error": f"unexpected:{type(e).__name__}:{str(e)}",
                    "record": record,
                }
            )

    payload = {
        "meta": {
            "input": str(input_path),
            "generated_at": datetime.now().isoformat(),
            "count": len(results),
            "failures": failures,
            "mode": args.mode,
            "top_k": args.top_k,
            "collection": args.collection,
        },
        "results": results,
    }

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    logger.info("Done: output=%s", str(output_path))
    return 0 if failures == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Run QA generation from raw consulting datasets")
    parser.add_argument("--input", required=True, help="input JSON file (list of raw records)")
    parser.add_argument("--output", required=True, help="output JSON file path")
    parser.add_argument("--limit", type=int, default=0, help="limit number of records (0 = no limit)")
    parser.add_argument("--mode", choices=["default", "force_json", "compact"], default="default")
    parser.add_argument("--top-k", type=int, default=None, help="override retrieval top_k")
    parser.add_argument("--collection", default="civil_cases_v1", help="Chroma collection name")
    parser.add_argument("--temperature", type=float, default=0.2, help="LLM temperature")
    args = parser.parse_args()

    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
