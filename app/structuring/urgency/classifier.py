"""B4 — 긴급도 보정 분류기 번들 (3-class + 확률 보정)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from app.structuring.urgency.dataset import LEVELS3
from app.structuring.urgency.features import build_matrix


class UrgencyModel:
    """embedder + 보정 분류기 묶음. predict(text, category) → 등급·확률."""

    def __init__(self, embedder: Any, clf: Any, classes: List[str] = None,
                 medium_threshold: float = 0.0):
        self.embedder = embedder
        self.clf = clf
        self.classes = list(classes or LEVELS3)
        self.medium_threshold = float(medium_threshold)  # P(보통)>=t & argmax=낮음 → 보통 승격

    def predict(self, text: str, category: str = "") -> Dict[str, Any]:
        rec = [{"text": text or "", "category": category or ""}]
        X = build_matrix(rec, self.embedder, fit=False)
        proba = self.clf.predict_proba(X)[0]
        order = list(self.clf.classes_)
        pdict = {cls: float(proba[order.index(cls)]) for cls in order}
        level = max(pdict, key=pdict.get)
        # 보통-우선 임계: 낮음으로 떨어진 경계 케이스를 보통으로 승격(소수 recall↑)
        if (self.medium_threshold > 0 and level == "낮음"
                and pdict.get("보통", 0.0) >= self.medium_threshold):
            level = "보통"
        return {"level": level, "proba": pdict, "score": float(max(proba))}

    def save(self, path: str) -> None:
        import joblib
        # bge-m3 등 비직렬화 모델 핸들 제거(지연 재로딩)
        if hasattr(self.embedder, "_model"):
            self.embedder._model = None
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"embedder": self.embedder, "clf": self.clf, "classes": self.classes,
                     "medium_threshold": self.medium_threshold}, path)

    @classmethod
    def load(cls, path: str) -> "UrgencyModel":
        import joblib
        d = joblib.load(path)
        return cls(d["embedder"], d["clf"], d.get("classes"), d.get("medium_threshold", 0.0))
