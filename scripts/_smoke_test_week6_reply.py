from __future__ import annotations

import json
import sys
import urllib.request


def _post_json(url: str, payload: dict, timeout_sec: int) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    base = "http://127.0.0.1:8000/api/v1"
    cases_path = "logs/evaluation/week6/seongnam_test_10_cases.json"

    with open(cases_path, "r", encoding="utf-8") as f:
        cases = json.load(f)

    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    case = cases[idx]
    query = case["query"]
    complaint_id = str(case.get("complaint_id") or case.get("case_id") or case.get("source_id") or "800806")

    search_payload = {
        "complaint_id": complaint_id,
        "query": query,
        "top_k": 6,
    }
    search_data = _post_json(base + "/search", search_payload, timeout_sec=120)

    routing_hint = search_data["data"]["routing_hint"]
    retrieved_docs = search_data["data"]["retrieved_docs"]

    qa_payload = {
        "complaint_id": complaint_id,
        "query": query,
        "routing_hint": routing_hint,
        "use_search_results": True,
        "search_results": [
            {
                "doc_id": d.get("doc_id") or d.get("case_id"),
                "chunk_id": d["chunk_id"],
                "case_id": d["case_id"],
                "snippet": d["snippet"],
                "score": d.get("score", d.get("similarity_score", 0.0)),
            }
            for d in retrieved_docs
        ],
    }
    qa_data = _post_json(base + "/qa", qa_payload, timeout_sec=240)

    answer = qa_data["data"]["answer"]
    print("--- ANSWER START ---")
    print(answer)
    print("--- ANSWER END ---")
    print("citations=", len(qa_data["data"].get("citations") or []))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
