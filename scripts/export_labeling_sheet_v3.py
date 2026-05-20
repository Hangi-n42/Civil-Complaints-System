"""V3 라벨링 시트 생성: qrels.tsv + queries + corpus_meta 를 하나의 CSV로 합치기"""

import json
import csv
from pathlib import Path

V3_DIR = Path("data/evaluation/v3")


def main():
    print("[*] V3 라벨링 시트 생성 중...")

    # 쿼리 로드
    queries = {}
    with (V3_DIR / "queries.jsonl").open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                obj = json.loads(line)
                queries[obj["query_id"]] = obj["query"]

    # 코퍼스 메타 로드 (case_id -> chunk_text 매핑)
    with (V3_DIR / "corpus_meta.json").open("r", encoding="utf-8") as f:
        corpus_list = json.load(f)
    corpus = {c["case_id"]: c["chunk_text"] for c in corpus_list}

    out_path = V3_DIR / "human_labeling_sheet_v3.csv"
    
    with (V3_DIR / "qrels.tsv").open("r", encoding="utf-8") as f_in, \
         out_path.open("w", encoding="utf-8-sig", newline="") as f_out:

        writer = csv.writer(f_out)
        writer.writerow([
            "Relevance_Score",   # 0~3 채울 곳 (빈칸)
            "Query_ID",
            "Query_Text",
            "Chunk_ID",          # case_id (CASE-XXXXXX)
            "Chunk_Text",
        ])

        next(f_in)  # 헤더 스킵
        count = 0
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != 4:
                continue

            qid, _, cid, _ = parts
            q_text = queries.get(qid, "N/A")
            c_text = corpus.get(cid, "N/A")

            writer.writerow(["", qid, q_text, cid, c_text])
            count += 1

    print(f"[OK] 완료! 총 {count}건 -> {out_path}")


if __name__ == "__main__":
    main()
