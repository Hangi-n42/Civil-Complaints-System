"""B5 — UrgencyScorer: 분류기 + 안전 오버라이드 + category SLA 결합.

최종 긴급도 = max( 분류기 등급(3-class), category SLA floor )  + 안전 오버라이드(→긴급).
- 모델(data/urgency/model.joblib) 있으면 사용, 없으면 규칙 폴백(LLM 비의존).
- 출력: {level, score, factors, evidence, override, model_level, method}.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from app.structuring.urgency.features import structured_features
from app.structuring.urgency.safety_rules import detect_safety

URGENCY_LEVELS = ["낮음", "보통", "높음", "긴급"]


def _max_level(a: str, b: str) -> str:
    ia = URGENCY_LEVELS.index(a) if a in URGENCY_LEVELS else 0
    ib = URGENCY_LEVELS.index(b) if b in URGENCY_LEVELS else 0
    return a if ia >= ib else b


class UrgencyScorer:
    def __init__(self, model_path: Optional[str] = None):
        from app.core.config import PROJECT_ROOT
        self.model_path = Path(model_path) if model_path else (PROJECT_ROOT / "data" / "urgency" / "model.joblib")
        self._model = None
        self._tried = False

    def _get_model(self):
        if not self._tried:
            self._tried = True
            try:
                from app.structuring.urgency.classifier import UrgencyModel
                if self.model_path.exists():
                    self._model = UrgencyModel.load(str(self.model_path))
            except Exception:
                self._model = None
        return self._model

    @staticmethod
    def _rule_fallback(safe: Dict[str, Any], feats: Dict[str, float]) -> str:
        if safe["safety_flag"] and safe["score"] >= 2:
            return "높음"
        if safe["safety_flag"] or feats["hazard_count"] > 0:
            return "보통"
        return "낮음"

    def score(self, text: str, category: str = "", category_floor: Optional[str] = None) -> Dict[str, Any]:
        text = text or ""
        safe = detect_safety(text)
        feats = structured_features(text, category)

        model = self._get_model()
        if model is not None:
            pred = model.predict(text, category)
            base_level, conf, method = pred["level"], pred["score"], "model"
        else:
            base_level, conf, method = self._rule_fallback(safe, feats), 0.5, "rule"

        level = base_level
        override = None
        # 안전 하드 오버라이드: 생명·신체 위협 + (등급 높음 or 다수 위협 신호) → 긴급
        if safe["safety_flag"] and (base_level == "높음" or safe["score"] >= 2):
            level, override = "긴급", "safety"
        # category SLA floor 결합(과소평가 방지)
        if category_floor:
            level = _max_level(level, category_floor)

        return {
            "level": level,
            "score": round(float(conf), 4),
            "factors": {
                "safety": min(int(safe["score"]), 3),
                "ongoing": bool(feats["ongoing"]),
                "recurring": bool(feats["recurring"]),
                "explicit_deadline": bool(feats["deadline"]),
            },
            "evidence": safe["evidence"],
            "override": override,
            "model_level": base_level,
            "method": method,
        }


_scorer: Optional[UrgencyScorer] = None


def get_urgency_scorer() -> UrgencyScorer:
    global _scorer
    if _scorer is None:
        _scorer = UrgencyScorer()
    return _scorer
