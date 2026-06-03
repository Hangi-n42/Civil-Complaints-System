"""
BE2 검색 평가셋 정비 — 논문용 그래프 생성.

reports/retrieval/v3/ 의 JSON 산출물을 읽어 4개 figure를 만든다(라벨은 영문, 렌더 안정):
  fig1_pooling_bias.png      풀링 편향: reranker 미판정율·격차 (before/after)
  fig2_self_reference.png    자기참조: WITH-self vs NO-self (RR@5, nDCG@10)
  fig3_final_ranking.png     최종 시스템 비교 (NO-self, 3채점관)
  fig4_judge_agreement.png   채점관 패널: ax4 vs Qwen 일치도·기권율

산출: reports/retrieval/v3/figures/*.png
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
REP = ROOT / "reports" / "retrieval" / "v3"
FIG = REP / "figures"
FIG.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({"font.size": 11, "axes.grid": True, "grid.alpha": 0.3, "figure.dpi": 150})
C = {"BM25": "#888888", "Dense": "#2c7fb8", "Reranker": "#d95f0e", "before": "#bbbbbb", "after": "#2c7fb8"}


def load(name):
    return json.loads((REP / name).read_text(encoding="utf-8"))


def g(m, key):
    for k, v in m.items():
        if k.lower() == key.lower():
            return float(v)
    return 0.0


def annotate(ax, bars, fmt="{:.3f}"):
    for b in bars:
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), fmt.format(b.get_height()),
                ha="center", va="bottom", fontsize=8)


def fig1_pooling():
    pre = load("reranker_condensed_eval_prepool.json")
    post = load("reranker_condensed_eval.json")
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))

    # (좌) reranker 미판정율
    u_pre = pre["unjudged_rate"]["top10"]["reranker"]
    u_post = post["unjudged_rate"]["top10"]["reranker"]
    bars = a1.bar(["Before pooling", "After pooling"], [u_pre, u_post], color=[C["before"], C["after"]])
    annotate(a1, bars, "{:.1%}")
    a1.set_title("Reranker top-10 unjudged rate")
    a1.set_ylabel("unjudged fraction")
    a1.set_ylim(0, max(u_pre, u_post) * 1.25)

    # (우) Dense-Reranker 격차 (표준 metric) before vs after
    keys = ["nDCG@10", "AP@10", "R@10"]
    gap_pre = [g(pre["standard"]["dense"], k) - g(pre["standard"]["reranker"], k) for k in keys]
    gap_post = [g(post["standard"]["dense"], k) - g(post["standard"]["reranker"], k) for k in keys]
    x = range(len(keys)); w = 0.38
    b1 = a2.bar([i - w / 2 for i in x], gap_pre, w, label="Before (biased)", color=C["before"])
    b2 = a2.bar([i + w / 2 for i in x], gap_post, w, label="After (fair pool)", color=C["after"])
    annotate(a2, b1); annotate(a2, b2)
    a2.set_xticks(list(x)); a2.set_xticklabels(keys)
    a2.set_title("Dense − Reranker gap (smaller = fairer)")
    a2.set_ylabel("metric gap")
    a2.legend()
    fig.suptitle("Pillar 1: Pooling-bias removal", fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "fig1_pooling_bias.png"); plt.close(fig)


def fig2_self_ref():
    e = load("eval_noself.json")
    sysns = ["BM25", "Dense", "Dense+Reranker"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax, key in ((a1, "RR@5"), (a2, "nDCG@10")):
        w = [g(e["with_self"][s], key) for s in sysns]
        n = [g(e["no_self"][s], key) for s in sysns]
        x = range(len(sysns)); ww = 0.38
        b1 = ax.bar([i - ww / 2 for i in x], w, ww, label="WITH self (inflated)", color=C["before"])
        b2 = ax.bar([i + ww / 2 for i in x], n, ww, label="NO self (realistic)", color=C["after"])
        annotate(ax, b1); annotate(ax, b2)
        ax.set_xticks(list(x)); ax.set_xticklabels(["BM25", "Dense", "Reranker"])
        ax.set_title(key); ax.set_ylim(0, 1.05)
        ax.legend(fontsize=9)
    fig.suptitle("Pillar 2: Self-reference removal (twin document excluded)", fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "fig2_self_reference.png"); plt.close(fig)


def fig3_final():
    e = load("eval_noself.json")
    sysns = ["BM25", "Dense", "Dense+Reranker"]
    labels = ["BM25", "Dense", "Reranker"]
    keys = ["nDCG@10", "AP@10", "R@10", "RR@5"]
    fig, ax = plt.subplots(figsize=(9, 4.6))
    x = range(len(keys)); w = 0.26
    for i, (s, lab) in enumerate(zip(sysns, labels)):
        vals = [g(e["no_self"][s], k) for k in keys]
        col = C["Dense"] if lab == "Dense" else (C["Reranker"] if lab == "Reranker" else C["BM25"])
        bars = ax.bar([xx + (i - 1) * w for xx in x], vals, w, label=lab, color=col)
        annotate(ax, bars, "{:.2f}")
    ax.set_xticks(list(x)); ax.set_xticklabels(keys)
    ax.set_title("Final realistic comparison (no-self, 3-judge median qrels)", fontweight="bold")
    ax.set_ylabel("score"); ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "fig3_final_ranking.png"); plt.close(fig)


def fig4_judges():
    ax4 = json.loads((ROOT / "data/evaluation/v3/fair_pool_validity_report.json").read_text(encoding="utf-8"))
    qw = json.loads((ROOT / "data/evaluation/v3/fair_pool_3judge_report.json").read_text(encoding="utf-8"))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))

    # (좌) 패널 Fleiss κ + pairwise (ax4 vs qwen)
    cats = ["Fleiss κ", "ex–gem", "ex–3rd", "gem–3rd"]
    ax4_v = [ax4["inter_rater_agreement"]["fleiss_kappa"], ax4["inter_rater_agreement"]["cohen_kappa_ex35_gem3"],
             ax4["inter_rater_agreement"]["cohen_kappa_ex35_ax4"], ax4["inter_rater_agreement"]["cohen_kappa_gem3_ax4"]]
    qw_v = [qw["inter_rater_agreement"]["fleiss_kappa"], qw["inter_rater_agreement"]["cohen_kappa_ex_gem"],
            qw["inter_rater_agreement"]["cohen_kappa_ex_qwen"], qw["inter_rater_agreement"]["cohen_kappa_gem_qwen"]]
    x = range(len(cats)); w = 0.38
    b1 = a1.bar([i - w / 2 for i in x], ax4_v, w, label="3rd = ax4 (weak)", color=C["before"])
    b2 = a1.bar([i + w / 2 for i in x], qw_v, w, label="3rd = Qwen2.5-14B", color=C["Dense"])
    annotate(a1, b1, "{:.2f}"); annotate(a1, b2, "{:.2f}")
    a1.axhline(0.4, ls="--", c="r", lw=1); a1.text(0, 0.41, "κ≥0.4 valid", color="r", fontsize=8)
    a1.set_xticks(list(x)); a1.set_xticklabels(cats); a1.set_title("Inter-rater agreement (3-judge panel)")
    a1.set_ylabel("kappa"); a1.legend(fontsize=9)

    # (우) 기권율
    ax4_abst = 1 - ax4["n_fully_scored"] / ax4["n_total_pairs"]
    qw_abst = 1 - qw["n_qwen_scored"] / qw["n_pool"]
    bars = a2.bar(["ax4", "Qwen2.5-14B"], [ax4_abst, qw_abst], color=[C["before"], C["Dense"]])
    annotate(a2, bars, "{:.0%}")
    a2.set_title("3rd-judge abstention rate (format non-compliance)")
    a2.set_ylabel("abstain fraction"); a2.set_ylim(0, max(ax4_abst, qw_abst) * 1.3 + 0.02)
    fig.suptitle("Pillar 3: Judge quality — ax4 → Qwen2.5-14B", fontweight="bold")
    fig.tight_layout()
    fig.savefig(FIG / "fig4_judge_agreement.png"); plt.close(fig)


def fig5_all_methods():
    """전체 5개 방법 종합 비교 (NO-self, 3채점관). 최종 결론 그래프."""
    base = load("eval_noself.json")["no_self"]          # BM25, Dense, Dense+Reranker
    hyb = load("eval_hybrid_noself.json")["no_self"]     # Hybrid(RRF)
    hyrr = load("eval_hybrid_reranked_noself.json")["no_self"]  # Hybrid+Reranker
    methods = {
        "BM25": base["BM25"],
        "Dense": base["Dense"],
        "Hybrid": hyb["Hybrid(RRF)"],
        "Dense+Rerank": base["Dense+Reranker"],
        "Hybrid+Rerank": hyrr["Hybrid+Reranker"],
    }
    colors = {"BM25": C["BM25"], "Dense": C["Dense"], "Hybrid": "#1a9850",
              "Dense+Rerank": C["Reranker"], "Hybrid+Rerank": "#984ea3"}
    keys = ["nDCG@10", "AP@10", "RR@5", "nDCG@5", "P@5"]
    fig, ax = plt.subplots(figsize=(11, 5))
    names = list(methods)
    x = range(len(keys)); w = 0.16
    for i, name in enumerate(names):
        vals = [g(methods[name], k) for k in keys]
        bars = ax.bar([xx + (i - 2) * w for xx in x], vals, w, label=name, color=colors[name])
        annotate(ax, bars, "{:.2f}")
    ax.set_xticks(list(x)); ax.set_xticklabels(keys)
    ax.set_title("Final method comparison (no-self, 3-judge median qrels) — Hybrid wins, reranker hurts",
                 fontweight="bold")
    ax.set_ylabel("score"); ax.legend(ncol=5, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, -0.08))
    fig.tight_layout()
    fig.savefig(FIG / "fig5_all_methods.png"); plt.close(fig)


if __name__ == "__main__":
    fig1_pooling(); fig2_self_ref(); fig3_final(); fig4_judges(); fig5_all_methods()
    print("figures →", FIG)
    for p in sorted(FIG.glob("*.png")):
        print(" ", p.name)
