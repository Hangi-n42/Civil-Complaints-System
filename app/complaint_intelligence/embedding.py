"""Complaint Intelligence Layer 임베딩 어댑터."""

from __future__ import annotations

import hashlib
import math
import re
from typing import Iterable, Protocol


class EmbeddingProvider(Protocol):
    """텍스트를 벡터로 변환하는 최소 인터페이스."""

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        """여러 텍스트를 임베딩한다."""


class FakeEmbeddingProvider:
    """테스트와 로컬 분석용 결정적 키워드 임베딩.

    외부 모델을 강제하지 않기 위해 sidecar 기본값으로 사용한다.
    """

    _KEYWORD_DIMENSIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("road_subsidence", ("싱크홀", "침하", "꺼짐", "구멍", "포트홀", "아스팔트", "도로", "움푹", "내려앉")),
        ("trash", ("쓰레기", "폐기물", "무단투기", "청소", "악취")),
        ("parking", ("주정차", "불법주정차", "주차", "단속", "차량")),
        ("streetlight", ("가로등", "보안등", "조명", "고장", "점멸")),
        ("noise", ("소음", "진동", "공사", "층간")),
        ("welfare", ("복지", "지원", "급여", "장애인", "노인")),
        ("water", ("누수", "하수", "상수도", "침수", "배수")),
        ("safety", ("위험", "안전", "사고", "파손", "균열")),
    )
    _TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]+")

    def embed(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        cleaned = str(text or "").lower()
        vector = [0.0 for _ in range(len(self._KEYWORD_DIMENSIONS) + 16)]
        for index, (_, keywords) in enumerate(self._KEYWORD_DIMENSIONS):
            for keyword in keywords:
                if keyword.lower() in cleaned:
                    vector[index] += 1.0

        for token in self._TOKEN_RE.findall(cleaned):
            digest = hashlib.sha1(token.encode("utf-8")).digest()
            vector[len(self._KEYWORD_DIMENSIONS) + digest[0] % 16] += 0.08

        return _normalize(vector)


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    """두 벡터의 cosine similarity를 계산한다."""

    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = sum(float(left[i]) * float(right[i]) for i in range(size))
    left_norm = math.sqrt(sum(float(item) ** 2 for item in left[:size]))
    right_norm = math.sqrt(sum(float(item) ** 2 for item in right[:size]))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def average_vectors(vectors: list[list[float]]) -> list[float]:
    """동일 차원 벡터들의 평균 벡터를 반환한다."""

    if not vectors:
        return []
    size = max(len(vector) for vector in vectors)
    averaged = []
    for index in range(size):
        averaged.append(sum(vector[index] if index < len(vector) else 0.0 for vector in vectors) / len(vectors))
    return _normalize(averaged)


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(item * item for item in vector))
    if norm == 0.0:
        return vector
    return [round(item / norm, 6) for item in vector]
