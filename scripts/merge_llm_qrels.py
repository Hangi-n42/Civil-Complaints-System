import csv
from pathlib import Path

V2_DIR = Path("data/evaluation/v2")

def main():
    llm_results_file = V2_DIR / "llm_results.csv"
    qrels_file = V2_DIR / "qrels.tsv"
    
    if not llm_results_file.exists() or not qrels_file.exists():
        print("[!] 필요한 파일이 없습니다.")
        return
    
    # 1. Parse LLM results
    scores = {}
    with llm_results_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            # Ignore empty lines, markdown formatting, and header rows
            if not line or line.startswith("```") or line.startswith("Query_ID"):
                continue
            
            parts = line.split(",")
            if len(parts) >= 3:
                qid = parts[0].strip()
                cid = parts[1].strip()
                try:
                    score = int(parts[2].strip())
                    scores[(qid, cid)] = str(score)
                except ValueError:
                    continue # Not a valid integer score
                    
    print(f"[*] 파싱된 LLM 라벨링 데이터 수: {len(scores)}건")
    
    # 2. Update qrels.tsv
    updated_lines = []
    unlabeled_count = 0
    with qrels_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split("\t")
            if len(parts) == 4:
                qid, zero, cid, old_score = parts
                
                # Check if we have an updated score
                new_score = scores.get((qid, cid))
                if new_score is not None:
                    updated_lines.append(f"{qid}\t{zero}\t{cid}\t{new_score}")
                else:
                    updated_lines.append(line)
                    if old_score == "-1":
                        unlabeled_count += 1
            else:
                updated_lines.append(line)
                
    # 3. Save back to qrels.tsv
    with qrels_file.open("w", encoding="utf-8") as f:
        for line in updated_lines:
            f.write(line + "\n")
            
    print(f"[*] 병합 완료! qrels.tsv가 업데이트 되었습니다.")
    if unlabeled_count > 0:
        print(f"[!] 경고: 여전히 '-1'로 남은 라벨이 {unlabeled_count}건 있습니다.")
    else:
        print("[OK] 모든 라벨링이 정상적으로 완료되었습니다 (-1 없음).")
    
if __name__ == "__main__":
    main()
