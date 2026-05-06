"""검색 평가 실행 산출물 저장 유틸리티."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable


def write_jsonl(path: str | Path, rows: Iterable[Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = asdict(row) if is_dataclass(row) else row
            handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            handle.write("\n")


def append_jsonl(path: str | Path, row: dict[str, Any]) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
        handle.write("\n")


def write_trec_run(path: str | Path, rows: Iterable[Any], run_name: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            qid = str(_get(row, "qid"))
            docid = str(_get(row, "docid"))
            rank = int(_get(row, "rank"))
            score = float(_get(row, "score"))
            handle.write(f"{qid} Q0 {docid} {rank} {score:.8f} {run_name}\n")


def _get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row[key]
    return getattr(row, key)

