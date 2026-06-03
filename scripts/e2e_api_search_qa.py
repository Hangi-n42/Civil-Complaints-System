"""E2E smoke test: /api/v1/search -> /api/v1/qa (use_search_results=true).

Usage:
  python scripts/e2e_api_search_qa.py --query "불법주정차 단속 요청" --top-k 3

Notes:
- Requires API server running (see scripts/run_api.py).
- This script intentionally keeps output short and actionable.
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any, Dict, List

import httpx


def _wait_for_health(client: httpx.Client, *, timeout_s: float) -> None:
    deadline = time.time() + timeout_s
    last_error: str | None = None

    while time.time() < deadline:
        try:
            resp = client.get("/api/v1/health")
            if resp.status_code == 200:
                return
            last_error = f"health status={resp.status_code} body={resp.text[:200]}"
        except Exception as exc:
            last_error = str(exc)

        time.sleep(0.25)

    raise RuntimeError(f"API health check failed: {last_error}")


def _to_qa_search_results(search_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    results = search_data.get("results") or search_data.get("items") or []
    qa_results: List[Dict[str, Any]] = []

    for item in results:
        if not isinstance(item, dict):
            continue
        qa_results.append(
            {
                "doc_id": item.get("doc_id"),
                "chunk_id": item.get("chunk_id"),
                "case_id": item.get("case_id"),
                "snippet": item.get("snippet") or "",
                "score": float(item.get("score", 0.0) or 0.0),
            }
        )

    return qa_results


def main() -> None:
    parser = argparse.ArgumentParser(description="E2E: search -> qa(use_search_results=true)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--query", required=True)
    parser.add_argument("--complaint-id", default="E2E-0001")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--collection", default="civil_cases_v1")
    parser.add_argument("--timeout-s", type=float, default=300.0)
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"

    timeout = httpx.Timeout(timeout=args.timeout_s)
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        _wait_for_health(client, timeout_s=20.0)

        search_payload = {
            "complaint_id": args.complaint_id,
            "query": args.query,
            "top_k": args.top_k,
            "filters": None,
            "collection_name": args.collection,
        }
        print(f"calling /search query={args.query!r} top_k={args.top_k}")
        search_resp = client.post("/api/v1/search", json=search_payload)
        print(f"/search status={search_resp.status_code}")
        if search_resp.status_code >= 400:
            print("/search error_body=", search_resp.text[:2000])
            search_resp.raise_for_status()
        search_json = search_resp.json()
        if not search_json.get("success", False):
            raise RuntimeError(f"/search failed: {json.dumps(search_json, ensure_ascii=False)[:1000]}")

        search_data = search_json.get("data") or {}
        routing_hint = search_data.get("routing_hint")
        routing_trace = search_data.get("routing_trace")
        results = search_data.get("results") or []
        print(
            f"/search ok result_count={len(results)} strategy_id={search_data.get('strategy_id')} route_key={search_data.get('route_key')}"
        )

        qa_search_results = _to_qa_search_results(search_data)
        qa_payload = {
            "complaint_id": args.complaint_id,
            "query": args.query,
            "top_k": args.top_k,
            "routing_hint": routing_hint,
            "routing_trace": routing_trace,
            "use_search_results": True,
            "search_results": qa_search_results,
            "filters": None,
        }

        print(f"calling /qa use_search_results=true count={len(qa_search_results)}")
        qa_resp = client.post("/api/v1/qa", json=qa_payload)
        print(f"/qa status={qa_resp.status_code}")
        if qa_resp.status_code >= 400:
            print("/qa error_body=", qa_resp.text[:2000])
            qa_resp.raise_for_status()
        qa_json = qa_resp.json()

        if not qa_json.get("success", False):
            raise RuntimeError(f"/qa failed: {json.dumps(qa_json, ensure_ascii=False)[:1000]}")

        qa_data = qa_json.get("data") or {}
        citations = qa_data.get("citations") or []
        answer = str(qa_data.get("answer") or "")

        print(
            f"/qa ok answer_chars={len(answer)} citations={len(citations)} model={((qa_json.get('meta') or {}).get('model'))}"
        )
        print("answer_preview=", answer[:300].replace("\n", " "))


if __name__ == "__main__":
    main()
