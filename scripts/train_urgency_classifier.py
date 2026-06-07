"""B4 — 긴급도 분류기 학습·평가 (5-fold CV + Platt 보정).

  python scripts/train_urgency_classifier.py                 # 기본 bge-m3 + GPU(cuda)
  python scripts/train_urgency_classifier.py --embedder tfidf  # 빠른 검증(모델 불필요)
  EMBEDDING_DEVICE=cpu python scripts/train_urgency_classifier.py  # GPU 없이 bge-m3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.structuring.urgency.dataset import LEVELS3, load_labeled_dataset  # noqa: E402
from app.structuring.urgency.features import Bge3Embedder, TfidfEmbedder, build_matrix  # noqa: E402
from app.structuring.urgency.classifier import UrgencyModel  # noqa: E402


def make_embedder(kind: str):
    if kind == "none":
        return None            # 구조화-only (임베딩/벡터화 없음, 완전 결정적)
    if kind == "bge3":
        import os
        return Bge3Embedder(device=os.getenv("EMBEDDING_DEVICE", "cuda"))
    return TfidfEmbedder()      # tfidf(기본): char n-gram + 구조화


def expected_calibration_error(probs, y_true_idx, n_bins=10):
    conf = probs.max(axis=1)
    pred = probs.argmax(axis=1)
    acc = (pred == y_true_idx).astype(float)
    ece, n = 0.0, len(conf)
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        m = (conf > lo) & (conf <= hi)
        if m.sum():
            ece += (m.sum() / n) * abs(acc[m].mean() - conf[m].mean())
    return ece


def main():
    from sklearn.calibration import CalibratedClassifierCV
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import classification_report, confusion_matrix, f1_score, recall_score
    from sklearn.model_selection import StratifiedKFold

    ap = argparse.ArgumentParser()
    ap.add_argument("--embedder", choices=["none", "tfidf", "bge3"], default="tfidf",
                    help="기본 tfidf(char n-gram+구조화, CPU). none=구조화-only, bge3=GPU(이점 없음).")
    ap.add_argument("--labels", default=str(ROOT / "data" / "urgency" / "labels.jsonl"))
    ap.add_argument("--data", default=str(ROOT / "data" / "processed" / "processed_consulting_data.json"),
                    help="전처리 데이터(민원인 원문). 상담사 답변 제외.")
    ap.add_argument("--out", default=str(ROOT / "data" / "urgency" / "model.joblib"))
    ap.add_argument("--medium-threshold", type=float, default=0.40, help="보통-우선 임계(0=off)")
    args = ap.parse_args()

    recs = load_labeled_dataset(args.labels, args.data)
    y = np.array([r["level3"] for r in recs])
    classes = LEVELS3
    cls_idx = {c: i for i, c in enumerate(classes)}
    y_idx = np.array([cls_idx[v] for v in y])
    from collections import Counter
    print(f"데이터: {len(recs)}건 | 분포: {dict(Counter(y))}")

    def new_clf():
        # 보정(CalibratedClassifierCV)은 불균형에서 소수(보통) recall 을 붕괴시켜 제외.
        # plain LR + class_weight balanced + 보통-우선 임계로 minority recall 확보.
        return LogisticRegression(max_iter=2000, class_weight="balanced", C=1.0)

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    all_pred, all_true, all_prob = [], [], []
    for tr, te in skf.split(recs, y):
        emb = make_embedder(args.embedder)
        Xtr = build_matrix([recs[i] for i in tr], emb, fit=True)
        Xte = build_matrix([recs[i] for i in te], emb, fit=False)
        clf = new_clf(); clf.fit(Xtr, y[tr])
        proba = clf.predict_proba(Xte)
        order = list(clf.classes_)
        prob_aligned = np.zeros((len(te), len(classes)))
        for j, c in enumerate(order):
            prob_aligned[:, cls_idx[c]] = proba[:, j]
        # 배포 모델과 동일한 보통-우선 임계 적용
        pred = prob_aligned.argmax(axis=1)
        bo = cls_idx["보통"]; lo = cls_idx["낮음"]
        if args.medium_threshold > 0:
            mask = (prob_aligned[:, bo] >= args.medium_threshold) & (pred == lo)
            pred[mask] = bo
        all_prob.append(prob_aligned)
        all_pred.extend(pred); all_true.extend(y_idx[te])

    all_pred = np.array(all_pred); all_true = np.array(all_true)
    all_prob = np.vstack(all_prob)
    print("\n=== 5-fold CV ===")
    print("macro-F1:", round(f1_score(all_true, all_pred, average='macro'), 4))
    for c, i in cls_idx.items():
        rec_c = recall_score(all_true == i, all_pred == i, zero_division=0)
        print(f"  recall[{c}]: {rec_c:.3f}")
    print("ECE:", round(expected_calibration_error(all_prob, all_true), 4))
    print("confusion (행=정답, 열=예측)", classes)
    print(confusion_matrix(all_true, all_pred))

    # 최종 모델(전체 학습) 저장
    emb = make_embedder(args.embedder)
    X = build_matrix(recs, emb, fit=True)
    clf = new_clf(); clf.fit(X, y)
    UrgencyModel(emb, clf, classes, medium_threshold=args.medium_threshold).save(args.out)
    print(f"\n저장: {args.out} (embedder={args.embedder})")


if __name__ == "__main__":
    main()
