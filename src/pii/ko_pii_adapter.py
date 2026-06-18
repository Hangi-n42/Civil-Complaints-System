from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


FORBIDDEN_MODES = {"PERMISSIVE", "AUDIT"}
FORBIDDEN_STRATEGIES = {"partial", "fpe", "tokenize"}
SAFE_MODE = "PARANOID"
SAFE_STRATEGY = "redact"


@dataclass(frozen=True)
class KoPiiAdapterResult:
    ok: bool
    text: str | None
    labels: list[str] = field(default_factory=list)
    label_counts: dict[str, int] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None


class KoPiiAdapter:
    """ko-pii를 RAG 저장 경로에서 안전한 설정으로만 호출한다."""

    def __init__(
        self,
        *,
        mode: Any = SAFE_MODE,
        strategy: str = SAFE_STRATEGY,
        engine: Any | None = None,
    ) -> None:
        mode_name = self._mode_name(mode)
        strategy_name = str(strategy or "").strip()
        if mode_name in FORBIDDEN_MODES or mode_name != SAFE_MODE:
            raise ValueError(f"ko-pii mode is not allowed for RAG: {mode_name}")
        if strategy_name in FORBIDDEN_STRATEGIES or strategy_name != SAFE_STRATEGY:
            raise ValueError(f"ko-pii strategy is not allowed for RAG: {strategy_name}")

        self.mode_name = mode_name
        self.strategy = strategy_name
        self._engine = engine

    @staticmethod
    def _mode_name(mode: Any) -> str:
        if hasattr(mode, "name"):
            return str(mode.name).strip().upper()
        raw = str(mode or "").strip()
        if "." in raw:
            raw = raw.rsplit(".", 1)[-1]
        return raw.upper()

    def _get_engine(self) -> Any:
        if self._engine is None:
            import ko_pii

            self._engine = ko_pii.Anonymizer(
                mode=ko_pii.ProcessingMode.PARANOID,
                strategy=SAFE_STRATEGY,
            )
        return self._engine

    def redact(self, text: str | None) -> KoPiiAdapterResult:
        try:
            source = "" if text is None else str(text)
            result = self._get_engine().process(source)
            masked_text = str(getattr(result, "text", "") or "")
            labels: list[str] = []
            for record in list(getattr(result, "detections", []) or []):
                detection = getattr(record, "detection", None)
                label = str(getattr(detection, "label", "") or "").strip().upper()
                if label:
                    labels.append(label)

            label_counts: dict[str, int] = {}
            for label in labels:
                label_counts[label] = label_counts.get(label, 0) + 1

            summary = getattr(result, "summary", {})
            return KoPiiAdapterResult(
                ok=True,
                text=masked_text,
                labels=labels,
                label_counts=label_counts,
                summary=summary if isinstance(summary, dict) else {},
            )
        except Exception:
            return KoPiiAdapterResult(
                ok=False,
                text=None,
                error_code="KO_PII_ERROR",
            )
