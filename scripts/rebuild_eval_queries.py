import sys
import asyncio
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.ingestion.service import get_ingestion_service
from app.structuring.service import get_structuring_service
from app.retrieval.service import get_retrieval_service

DATA_DIR = project_root / "data" / "evaluation"
V2_DIR = DATA_DIR / "v2"

def _load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

async def main():
    queries_path = DATA_DIR / "retrieval_eval_gold50.json"
    chunks_path = DATA_DIR / "retrieval_chunk_pool.json"
    
    if not queries_path.exists() or not chunks_path.exists():
        print("[!] Missing gold50 or chunk_pool JSON files.")
        return

    queries = _load_json(queries_path)
    chunks = _load_json(chunks_path)
    chunks_by_source = {c.get("source_id"): c for c in chunks}
    
    structuring = get_structuring_service()
    
    print("[*] 50개 평가 쿼리에 대해 LLM 구조화를 진행합니다... (Exaone)")
    
    v2_queries = []
    
    for idx, q in enumerate(queries, 1):
        q_source_id = q.get("source_id")
        chunk = chunks_by_source.get(q_source_id)
        
        final_query_text = q["query"]
        if chunk:
            raw_text = chunk.get("chunk_text", "")
            try:
                # Structure
                proc = {"text": raw_text, "raw_text": raw_text, "source_id": q_source_id}
                structured = await structuring.structure(proc)
                
                if structured:
                    obs = structured.get("observation", {})
                    res = structured.get("result", {})
                    req = structured.get("request", {})
                    ctx = structured.get("context", {})

                    sections = []
                    for field in (obs, res, req, ctx):
                        if isinstance(field, dict) and field.get("text"):
                            val = field["text"].strip()
                            if val and val not in ("없음", "해당없음", "-", "N/A"):
                                sections.append(val)
                    
                    if sections:
                        final_query_text = "\n".join(sections)
            except Exception as e:
                print(f"[!] Error on {q_source_id}: {e}")
                
        v2_queries.append({
            "query_id": q["query_id"],
            "query": final_query_text,
            "source_id": q_source_id,
            "source": q.get("source", ""),
            "category": q.get("consulting_category", "")
        })
        
        print(f"  - {idx}/{len(queries)} 완료")
        
    V2_DIR.mkdir(parents=True, exist_ok=True)
    out_path = V2_DIR / "queries.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for q in v2_queries:
            f.write(json.dumps(q, ensure_ascii=False) + "\n")
            
    print(f"[*] {out_path} 저장 완료")

if __name__ == "__main__":
    asyncio.run(main())
