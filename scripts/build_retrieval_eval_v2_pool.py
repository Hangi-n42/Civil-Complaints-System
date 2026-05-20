"""
Build V2 Retrieval Evaluation Pool

이 스크립트는 평가용 50개 쿼리에 대해 BM25와 BGE-m3 임베딩을 이용해
Top-10 후보들을 추출한 뒤, 합집합 풀을 생성합니다.
라벨링 부담을 줄이기 위해 일부 규칙(동일 source + 동일 category)에 해당하는
후보에는 자동으로 1점을 부여하며, Leak 방지를 위해 동일 source_id는 후보에서 제외합니다.
"""

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import List, Dict, Any, Set

try:
    from sentence_transformers import SentenceTransformer
    import torch
except ImportError:
    SentenceTransformer = None

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "evaluation"
V2_DIR = DATA_DIR / "v2"


class BM25:
    """간단한 인메모리 BM25 구현"""
    def __init__(self, corpus: List[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.avgdl = 0
        self.doc_freqs = []
        self.idf = {}
        self.doc_len = []
        self._initialize(corpus)

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[A-Za-z0-9가-힣]+", text.lower())

    def _initialize(self, corpus: List[str]):
        nd = {}
        num_doc = 0
        for document in corpus:
            self.doc_len.append(0)
            num_doc += len(document)
            frequencies = Counter(self._tokenize(document))
            self.doc_freqs.append(frequencies)
            for word, freq in frequencies.items():
                nd[word] = nd.get(word, 0) + 1
            self.doc_len[-1] = sum(frequencies.values())
        
        self.avgdl = num_doc / self.corpus_size if self.corpus_size else 0
        for word, freq in nd.items():
            # 기본 IDF 수식
            self.idf[word] = math.log(((self.corpus_size - freq + 0.5) / (freq + 0.5)) + 1)

    def get_scores(self, query: str) -> List[float]:
        score = [0.0] * self.corpus_size
        q_tokens = self._tokenize(query)
        for q in q_tokens:
            if q not in self.idf:
                continue
            for i in range(self.corpus_size):
                f = self.doc_freqs[i].get(q, 0)
                if f == 0:
                    continue
                numerator = self.idf[q] * f * (self.k1 + 1)
                denominator = f + self.k1 * (1 - self.b + self.b * self.doc_len[i] / self.avgdl)
                score[i] += numerator / denominator
        return score


def load_jsonl(path: Path) -> List[Any]:
    data = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main():
    print("[*] V2 후보 풀 생성 시작")
    V2_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. 데이터 로드
    queries_path = V2_DIR / "queries.jsonl"
    chunks_path = DATA_DIR / "retrieval_chunk_pool_structured.json"
    
    if not queries_path.exists() or not chunks_path.exists():
        print(f"[!] 에러: {queries_path.name} 또는 {chunks_path.name} 파일이 없습니다.")
        return
        
    queries = load_jsonl(queries_path)
    chunks = load_json(chunks_path)
    print(f"[*] 로드 완료: 쿼리 {len(queries)}건, 청크 {len(chunks)}건")
    
    # 2. BM25 초기화
    print("[*] BM25 모델 초기화 중...")
    chunk_texts = [c.get("chunk_text", "") for c in chunks]
    bm25_model = BM25(chunk_texts)
    
    # 3. Dense (BGE-m3) 초기화
    if SentenceTransformer is None:
        print("[!] 에러: sentence-transformers 패키지가 필요합니다.")
        return
        
    print("[*] BGE-m3 모델 로드 및 임베딩 중...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    embed_model = SentenceTransformer("BAAI/bge-m3", device=device)
    chunk_embeddings = embed_model.encode(chunk_texts, convert_to_tensor=True)
    
    # 결과 저장용 리스트
    v2_queries = []
    qrels_lines = []
    
    qrels_lines.append("query_id\t0\tchunk_id\trelevance")
    
    total_candidates = 0
    auto_labeled = 0
    
    print("[*] 쿼리별 후보 추출 진행 중...")
    for idx, q in enumerate(queries, 1):
        q_id = q["query_id"]
        q_text = q["query"]
        q_source_id = q.get("source_id", "")
        q_source = q.get("source", "")
        q_category = q.get("category", "")
        
        v2_queries.append({
            "query_id": q_id,
            "query": q_text,
            "source_id": q_source_id,
            "source": q_source,
            "category": q_category
        })
        
        # 4. 점수 계산
        bm25_scores = bm25_model.get_scores(q_text)
        
        q_emb = embed_model.encode([q_text], convert_to_tensor=True)
        dense_scores = (q_emb @ chunk_embeddings.T).squeeze().tolist()
        
        # Rank chunks
        bm25_ranked = sorted(range(len(chunks)), key=lambda i: bm25_scores[i], reverse=True)
        dense_ranked = sorted(range(len(chunks)), key=lambda i: dense_scores[i], reverse=True)
        
        # Top 10 합집합 (인덱스 기준)
        top_k = 10
        pool_indices = set(bm25_ranked[:top_k]) | set(dense_ranked[:top_k])
        
        # 5. 규칙 적용 (Leak 방지 및 자동 라벨링)
        for chunk_idx in pool_indices:
            c = chunks[chunk_idx]
            c_id = c["chunk_id"]
            c_source_id = c.get("source_id", "")
            
            # Leak 방지: 자기 자신은 정답 후보에서 완전히 제외
            if q_source_id and c_source_id and q_source_id == c_source_id:
                continue
                
            # 자동 보강: 동일 source + 동일 category 인 경우 1점 부여
            c_source = c.get("source", "")
            c_category = c.get("category", "")
            
            relevance = -1  # -1 은 사람이 직접 라벨링 해야 함을 의미
            if q_source and c_source and q_source == c_source:
                if q_category and c_category and q_category == c_category:
                    relevance = 1
                    auto_labeled += 1
                    
            qrels_lines.append(f"{q_id}\t0\t{c_id}\t{relevance}")
            total_candidates += 1
            
        if idx % 10 == 0:
            print(f"  - {idx}/{len(queries)} 처리 완료")
            
    # 6. 산출물 저장
    save_json(V2_DIR / "corpus.jsonl", chunks)
    
    qrels_path = V2_DIR / "qrels.tsv"
    qrels_path.write_text("\n".join(qrels_lines) + "\n", encoding="utf-8")
    
    manifest = {
        "generated_at": "auto",
        "description": "V2 Evaluation Pool created by BM25 and BGE-m3",
        "total_queries": len(queries),
        "total_candidates": total_candidates,
        "auto_labeled_count": auto_labeled,
        "human_label_required": total_candidates - auto_labeled
    }
    save_json(V2_DIR / "manifest.json", manifest)
    
    print("\n[OK] V2 후보 풀 생성 완료!")
    print(f" - 총 평가 쿼리: {len(queries)}건")
    print(f" - 총 추출된 후보: {total_candidates}건 (쿼리당 평균 {total_candidates/len(queries):.1f}건)")
    print(f" - 자동 라벨링(1점) 처리: {auto_labeled}건")
    print(f" - 사람 라벨링 필요(relevance=-1): {total_candidates - auto_labeled}건")
    print(f"\n산출물 위치: {V2_DIR}")
    print(" 1) qrels.tsv (라벨링용)")
    print(" 2) corpus.jsonl, queries.jsonl (데이터 참조용)")

if __name__ == "__main__":
    main()
