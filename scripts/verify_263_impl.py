"""#263 구현 검증: 정리된 search()의 Adaptive가 Dense와 동등하고 경고 없는지 확인."""
import sys, logging
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# "BM25 검색 실패" 경고가 더 이상 발생하지 않는지 감지
warned = {"bm25_fail": False}
class _Catch(logging.Handler):
    def emit(self, record):
        if "BM25 검색 실패" in record.getMessage():
            warned["bm25_fail"] = True
logging.getLogger().addHandler(_Catch())
logging.getLogger().setLevel(logging.WARNING)

from scripts.run_v3_evaluation import load_queries, load_qrels, run_dense, run_adaptive, compute_metrics

def _m(d, k):
    for kk, vv in d.items():
        if kk.lower() == k.lower():
            return vv
    return 0.0

queries = load_queries()
qrels = load_qrels()
print(f"쿼리 {len(queries)} / qrels {len(qrels)}")

adaptive = compute_metrics(run_adaptive(queries), qrels)
dense = compute_metrics(run_dense(queries), qrels)

print(f"\n{'metric':<10}{'Adaptive(정리)':>16}{'Dense':>10}{'Δ':>10}")
for k in ["nDCG@5", "nDCG@10", "R@10", "AP@10", "P@5"]:
    a, d = _m(adaptive, k), _m(dense, k)
    print(f"{k:<10}{a:>16.4f}{d:>10.4f}{a-d:>+10.4f}")

print(f"\n'BM25 검색 실패' 경고 발생: {warned['bm25_fail']}  (기대: False)")
ok = (not warned['bm25_fail']) and abs(_m(adaptive,'nDCG@5') - _m(dense,'nDCG@5')) < 0.01
print(f"판정: {'PASS — Adaptive=Dense, 경고 없음' if ok else 'CHECK 필요'}")
