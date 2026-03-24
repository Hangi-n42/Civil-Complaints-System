"""Week 2 BE2: ChromaDB 컬렉션/필터 점검 스크립트."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings
from app.retrieval.vectorstores.chroma_validation import run_chromadb_filter_validation


def main() -> int:
    parser = argparse.ArgumentParser(description="ChromaDB 메타데이터 필터 점검")
    parser.add_argument(
        "--persist-dir",
        type=str,
        default=settings.CHROMA_DB_PATH,
        help="ChromaDB persist 경로",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default="week2_be2_filter_check",
        help="점검 대상 컬렉션 이름",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(Path("logs") / "evaluation" / "week2_be2_chromadb_filter_report.json"),
        help="점검 리포트 출력 경로",
    )
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="컬렉션 초기화 없이 점검 실행",
    )
    args = parser.parse_args()

    report = run_chromadb_filter_validation(
        persist_directory=args.persist_dir,
        collection_name=args.collection,
        reset_collection=not args.no_reset,
    )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("status") == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
