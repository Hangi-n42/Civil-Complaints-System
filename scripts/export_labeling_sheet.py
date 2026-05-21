import json
import csv
from pathlib import Path

V2_DIR = Path("data/evaluation/v2")

def load_jsonl(path):
    data = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                obj = json.loads(line)
                # handle both queries and corpus key differences
                key = obj.get("query_id") or obj.get("chunk_id")
                data[key] = obj
    return data

def main():
    print("라벨링용 통합 스프레드시트 생성 중...")
    
    queries = load_jsonl(V2_DIR / "queries.jsonl")
    with (V2_DIR / "corpus.jsonl").open("r", encoding="utf-8") as f:
        corpus_list = json.load(f)
        corpus = {c.get("chunk_id"): c for c in corpus_list if isinstance(c, dict)}
    
    out_path = V2_DIR / "human_labeling_sheet_final.csv"
    
    with (V2_DIR / "qrels.tsv").open("r", encoding="utf-8") as f_in, \
         out_path.open("w", encoding="utf-8-sig", newline="") as f_out:  # utf-8-sig for Excel compatibility
        
        writer = csv.writer(f_out)
        
        # 헤더 작성
        writer.writerow([
            "Relevance_Score", 
            "Query_ID", 
            "Query_Text", 
            "Chunk_ID", 
            "Chunk_Text",
            "Auto_Labeled"
        ])
        
        next(f_in) # skip tsv header
        
        count = 0
        for line in f_in:
            line = line.strip()
            if not line: continue
            
            parts = line.split("\t")
            if len(parts) < 4: continue
            
            qid, _, cid, rel = parts[0], parts[1], parts[2], parts[3]
            
            # 수동 라벨링 대상(-1)만 필터링할지 고민이지만, 일단 전체를 다 씁니다.
            # 1점 자동할당된 것도 볼 수 있게 표시
            is_auto = "O (자동 1점)" if rel == "1" else "X (라벨링 필요)"
            score_to_write = "1" if rel == "1" else ""  # -1은 빈칸으로 두어 사람이 채우게 함
            
            q_text = queries.get(qid, {}).get("query", "N/A")
            c_text = corpus.get(cid, {}).get("chunk_text", "N/A")
            
            writer.writerow([
                score_to_write,
                qid,
                q_text,
                cid,
                c_text,
                is_auto
            ])
            count += 1
            
    print(f"완료! 총 {count}건의 쌍이 {out_path} 에 저장되었습니다.")

if __name__ == "__main__":
    main()
