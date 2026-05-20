"""
qrels.tsv의 AIHUB-XXXXXX__chunk-0 형태 chunk_id를
ChromaDB 실제 case_id(CASE-XXXXXX) 기준으로 재매핑하는 스크립트.

매핑 규칙:
  AIHUB-700890__chunk-0 -> CASE-700890  (소스 번호 그대로, 접두사만 교체)
  
주의: 평가 시 retrieved 결과도 chunk_id 전체가 아닌 case_id 기준으로 매칭한다.
"""

from pathlib import Path

V2_DIR = Path("data/evaluation/v2")

def aihub_to_case_id(chunk_id: str) -> str:
    """AIHUB-XXXXXX__chunk-0 -> CASE-XXXXXX 변환."""
    # AIHUB-700890__chunk-0 -> 700890
    num = chunk_id.replace("AIHUB-", "").split("__chunk-")[0]
    return f"CASE-{num}"

def main():
    qrels_path = V2_DIR / "qrels.tsv"
    out_path = V2_DIR / "qrels_caseid.tsv"
    
    with qrels_path.open("r", encoding="utf-8") as f_in, \
         out_path.open("w", encoding="utf-8") as f_out:
        
        header = next(f_in)
        f_out.write(header)
        
        count = 0
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) == 4:
                qid, zero, chunk_id, score = parts
                # AIHUB chunk_id -> CASE- case_id 변환
                case_id = aihub_to_case_id(chunk_id)
                f_out.write(f"{qid}\t{zero}\t{case_id}\t{score}\n")
                count += 1
    
    print(f"[*] 변환 완료: {count}건 -> {out_path}")
    print(f"[*] 샘플 변환 예시: AIHUB-700890__chunk-0 -> CASE-700890")

if __name__ == "__main__":
    main()
