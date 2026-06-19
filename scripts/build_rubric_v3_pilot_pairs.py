"""v3 루브릭 파일럿용 (쿼리, 후보) 쌍 + 텍스트 추출.

기존 qrels_final 에서 라벨(0/1/2)별로 골고루 쌍을 뽑고, 각 민원의 실제 텍스트를
원천 데이터에서 가져온다. 쿼리는 민원인 원문(중립), 후보는 질문+상담사 답변
(generic_boilerplate 등 판단을 위해 답변 포함). v3 루브릭으로 채점한 뒤 기존 라벨과
대조하기 위한 파일럿 입력을 만든다. 원문은 평가용으로만 사용(집계 외 비공개).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.structuring.preprocessing import _prepared_record, civil_text, civil_text_with_answer
from scripts.eval_be1_metadata_overlay_soft_rerank import load_qrels

QUERIES = PROJECT_ROOT / "data" / "evaluation" / "version_neutral" / "queries.jsonl"
QRELS = PROJECT_ROOT / "data" / "evaluation" / "v3" / "qrels_final.tsv"
SRC_DIR = PROJECT_ROOT / "data" / "Public_Civil_Service_LLM_Data"
OUT = PROJECT_ROOT / "reports" / "retrieval" / "version_neutral" / "rubric_v3_pilot_pairs.json"
PER_LABEL = 8


def build_source_map() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for f in sorted(SRC_DIR.rglob("*.json")):
        try:
            data = json.load(open(f, encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        for item in data if isinstance(data, list) else [data]:
            sid = str(item.get("source_id") or "")
            if sid and sid not in out:
                out[sid] = item
    return out


def main() -> int:
    queries = {}
    for line in QUERIES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            queries[row["query_id"]] = row
    qrels = load_qrels(QRELS)
    smap = build_source_map()

    def chunk_text(docid: str) -> str | None:
        sid = docid.replace("CASE-", "")
        raw = smap.get(sid)
        return civil_text_with_answer(_prepared_record(raw)) if raw else None

    by_label: dict[int, list] = {0: [], 1: [], 2: []}
    for r in qrels:
        if r.qid in queries and r.relevance in by_label:
            by_label[r.relevance].append(r)

    pairs = []
    for label in (0, 1, 2):
        picked, seen_q = 0, set()
        for r in sorted(by_label[label], key=lambda x: (x.qid, x.docid)):
            if picked >= PER_LABEL:
                break
            if r.qid in seen_q:  # 쿼리 다양성
                continue
            q = queries[r.qid]["query"].strip()
            c = chunk_text(r.docid)
            if not q or not c:
                continue
            seen_q.add(r.qid)
            picked += 1
            pairs.append({
                "qid": r.qid, "docid": r.docid, "existing_label": label,
                "query": q[:1500], "chunk": c[:2000],
            })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(pairs, ensure_ascii=False, indent=2), encoding="utf-8")
    dist = {l: sum(1 for p in pairs if p["existing_label"] == l) for l in (0, 1, 2)}
    print(f"[pilot] 원천 {len(smap)} | 추출 {len(pairs)}쌍 | 라벨분포 {dist}")
    print(f"[write] {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
