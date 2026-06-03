import sys
import asyncio
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.structuring.service import get_structuring_service

DATA_DIR = project_root / "data" / "evaluation"

def _load_json(path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def _save_json(path, data):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

async def main():
    chunks_path = DATA_DIR / "retrieval_chunk_pool.json"
    if not chunks_path.exists():
        print("[!] Missing chunk_pool.json")
        return
        
    chunks = _load_json(chunks_path)
    structuring = get_structuring_service()
    
    print(f"[*] {len(chunks)}개 청크에 대해 LLM 구조화를 진행합니다... (Exaone)")
    
    for idx, chunk in enumerate(chunks, 1):
        raw_text = chunk.get("chunk_text", "")
        
        try:
            proc = {"text": raw_text, "raw_text": raw_text, "source_id": chunk.get("source_id")}
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
                    chunk["chunk_text"] = "\n".join(sections)
                    
        except Exception as e:
            print(f"[!] Error on {chunk.get('chunk_id')}: {e}")
            
        if idx % 10 == 0:
            print(f"  - {idx}/{len(chunks)} 완료")
            
    out_path = DATA_DIR / "retrieval_chunk_pool_structured.json"
    _save_json(out_path, chunks)
    print(f"[*] 완료. 구조화된 청크 {out_path} 에 저장됨.")

if __name__ == "__main__":
    asyncio.run(main())
