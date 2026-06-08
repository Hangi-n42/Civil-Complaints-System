"""B3 — 긴급도 피처 빌더.

피처 = [텍스트 임베딩] ⊕ [구조화 피처(결정적)].
- 임베딩 embedder 는 주입형: 운영=bge-m3, 검증/폴백=TF-IDF(char n-gram).
- 구조화 피처: 안전(B2), 위험어 수, 진행/반복/기한 마커, 본문 길이, 카테고리 도메인 플래그.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence

import numpy as np

from app.structuring.urgency.safety_rules import detect_safety
from app.structuring.enrichment import FACILITY_KEYWORDS

_HAZARD_WORDS = ["소음", "악취", "분진", "먼지", "누수", "파손", "균열", "침수", "사고",
                 "위험", "붕괴", "고장", "오염", "악화", "심각"]
_ONGOING = re.compile(r"지금|현재|계속|진행\s*중|아직도|여전|상시")
_RECURRING = re.compile(r"매일|매번|상습|반복|마다|수차례|또다시|자꾸|늘")
_DEADLINE = re.compile(r"까지|마감|기한|임박|모레|내일|곧|시급|당장")
# 보통/낮음 경계 신호(조치 요구·영향범위·심각도). Δrecall 입증된 것만.
_ACTION = re.compile(r"보수|수리|교체|정비|철거|설치|단속|점검|조치|복구|시정|개선|정상화")
_IMPACT = re.compile(r"다수|시민|주민|모두|전체|불특정|통행|이용자|보행자|아이들|학생|어르신|입주민")
_SEVERITY = re.compile(r"불편|피해|심각|막혀|막힘|고장|파손|방치|악화|훼손|위험")
# 카테고리(consulting_category) 도메인 플래그
_CAT_FLAGS = {
    "cat_safety": re.compile(r"안전|재난|소방|구조물"),
    "cat_road": re.compile(r"도로|교통|버스|주차"),
    "cat_env": re.compile(r"환경|하천|청소|폐기|자원순환|위생|보건"),
    "cat_park": re.compile(r"공원|녹지|체육|산림"),
    "cat_welfare": re.compile(r"복지|노인|아동|여성|장애|보육"),
    "cat_build": re.compile(r"건축|주택|도시|정비"),
}

STRUCT_FEATURE_NAMES: List[str] = (
    ["safety_flag", "safety_score", "text_len", "hazard_count",
     "ongoing", "recurring", "deadline",
     "action", "facility_count", "impact", "severity"] + list(_CAT_FLAGS.keys())
)


def structured_features(text: str, category: str = "") -> Dict[str, float]:
    """결정적 구조화 피처(이름→값). 모든 값 [0,1] 정규화."""
    text = text or ""
    cat = category or ""
    safe = detect_safety(text)
    hz = sum(1 for w in _HAZARD_WORDS if w in text)
    feats = {
        "safety_flag": float(safe["safety_flag"]),
        "safety_score": min(safe["score"] / 5.0, 1.0),
        "text_len": min(len(text) / 1500.0, 1.0),
        "hazard_count": min(hz / 6.0, 1.0),
        "ongoing": 1.0 if _ONGOING.search(text) else 0.0,
        "recurring": 1.0 if _RECURRING.search(text) else 0.0,
        "deadline": 1.0 if _DEADLINE.search(text) else 0.0,
        "action": 1.0 if _ACTION.search(text) else 0.0,          # 조치 요구 → 보통 신호
        "facility_count": min(sum(1 for w in FACILITY_KEYWORDS if w in text) / 4.0, 1.0),
        "impact": 1.0 if _IMPACT.search(text) else 0.0,          # 다수·공공 영향
        "severity": 1.0 if _SEVERITY.search(text) else 0.0,      # 불편·피해·심각
    }
    for name, rx in _CAT_FLAGS.items():
        feats[name] = 1.0 if rx.search(cat) else 0.0
    return feats


def structured_matrix(records: Sequence[Dict[str, Any]]) -> np.ndarray:
    rows = []
    for r in records:
        f = structured_features(r.get("text", ""), r.get("category", ""))
        rows.append([f[n] for n in STRUCT_FEATURE_NAMES])
    return np.asarray(rows, dtype="float32")


# ── 임베더 ────────────────────────────────────────────────────────────────
class TfidfEmbedder:
    """검증/폴백용 char n-gram TF-IDF (모델 다운로드 불필요)."""

    def __init__(self, max_features: int = 3000):
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4),
                                   max_features=max_features)
        self._fitted = False

    def fit(self, texts: Sequence[str]) -> "TfidfEmbedder":
        self.vec.fit(list(texts)); self._fitted = True; return self

    def transform(self, texts: Sequence[str]) -> np.ndarray:
        return self.vec.transform(list(texts)).toarray().astype("float32")


class Bge3Embedder:
    """운영용 bge-m3 임베더(로컬, GPU 권장). fit 은 no-op."""

    def __init__(self, model_name: str = "BAAI/bge-m3", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _m(self):
        if self._model is None:
            dev = self.device
            if dev == "cuda":
                try:
                    import torch
                    if not torch.cuda.is_available():
                        dev = "cpu"
                except Exception:
                    dev = "cpu"
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=dev)
        return self._model

    def fit(self, texts: Sequence[str]) -> "Bge3Embedder":
        return self

    def transform(self, texts: Sequence[str]) -> np.ndarray:
        v = self._m().encode(list(texts), convert_to_numpy=True, normalize_embeddings=True)
        return np.asarray(v, dtype="float32")


def build_matrix(records: Sequence[Dict[str, Any]], embedder, fit: bool = False,
                 struct_scale: float = 4.0) -> np.ndarray:
    """[임베딩 ⊕ 구조화×struct_scale] 결합 행렬.

    struct_scale: 결정적 구조화 피처가 고차원 임베딩에 묻히지 않도록 가중(>=1).
    """
    struct = structured_matrix(records) * float(struct_scale)
    if embedder is None:           # 구조화-only (임베딩 제거 — 소수 클래스 recall 우수)
        return struct.astype("float32")
    texts = [r.get("text", "") for r in records]
    if fit:
        embedder.fit(texts)
    emb = embedder.transform(texts)
    return np.hstack([emb, struct]).astype("float32")
