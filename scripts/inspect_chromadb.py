"""ChromaDB 저장 데이터 점검/덤프 스크립트.

목적:
- 로컬 persist 경로(data/chroma_db 등)에 저장된 ChromaDB 컬렉션을 빠르게 확인한다.
- 컬렉션 목록, count, 샘플 레코드 출력, JSONL 덤프를 지원한다.

예시:
  # 컬렉션 목록
  python scripts/inspect_chromadb.py list

  # count 확인
  python scripts/inspect_chromadb.py count --collection civil_cases_v1

  # 상위 5개 샘플 출력
  python scripts/inspect_chromadb.py sample --collection civil_cases_v1 --limit 5

  # 전체 덤프(JSONL)
  python scripts/inspect_chromadb.py dump --collection civil_cases_v1 --output logs/chroma/civil_cases_v1.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings


def _normalize_persist_dir_for_chroma(persist_dir: str | Path) -> str:
    """Chroma PersistentClient에 전달할 경로를 정규화한다.

    Windows에서 한글이 포함된 절대 경로를 Rust 바인딩이 제대로 처리하지 못해
    `Error loading hnsw index`가 재현되는 경우가 있어, 프로젝트 루트 내부 경로면
    상대 경로로 우회한다.
    """

    path = Path(persist_dir)
    client_path = str(path)

    try:
        resolved = path.resolve()
    except Exception:
        return client_path

    # 1) CWD 기준 relpath를 우선 사용한다.
    #    Chroma는 상대 경로를 현재 작업 디렉터리 기준으로 해석하므로,
    #    상위 폴더에서 스크립트를 실행해도 올바른 persist 폴더를 가리키게 된다.
    try:
        cwd = Path.cwd().resolve()
        client_path = os.path.relpath(str(resolved), start=str(cwd))
    except Exception:
        client_path = str(path)

    # 2) 일부 환경에서 relpath 계산이 불가능하면(드라이브/UNC 등) 프로젝트 루트 기준도 시도한다.
    if client_path == str(path):
        try:
            root = project_root.resolve()
            if resolved == root or root in resolved.parents:
                client_path = str(resolved.relative_to(root))
        except Exception:
            pass

    return client_path


def _try_import_chromadb():
    try:
        import chromadb  # type: ignore

        return chromadb
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "chromadb import에 실패했습니다. requirements 설치/가상환경을 확인하세요."
        ) from exc


def _looks_like_hnsw_load_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "hnsw" in message and "error" in message and "load" in message


def _sqlite_db_path(persist_dir: Path) -> Path:
    return persist_dir / "chroma.sqlite3"


def _sqlite_connect(persist_dir: Path) -> sqlite3.Connection:
    db_path = _sqlite_db_path(persist_dir)
    if not db_path.exists():
        raise RuntimeError(f"sqlite 파일을 찾지 못했습니다: {db_path}")
    return sqlite3.connect(str(db_path))


def _sqlite_tables(con: sqlite3.Connection) -> List[str]:
    cur = con.cursor()
    cur.execute("select name from sqlite_master where type='table' order by name")
    return [row[0] for row in cur.fetchall()]


def _sqlite_columns(con: sqlite3.Connection, table: str) -> List[str]:
    cur = con.cursor()
    cur.execute(f"pragma table_info({table})")
    return [row[1] for row in cur.fetchall()]


def _sqlite_docs(
    *,
    persist_dir: Path,
    collection_name: str,
    limit: int,
    max_chars: int,
) -> Dict[str, Any]:
    con = _sqlite_connect(persist_dir)
    try:
        tables = _sqlite_tables(con)
        tables_set = set(tables)
        required = {"collections", "segments", "embeddings", "embedding_metadata"}
        missing = sorted(required - tables_set)
        if missing:
            return {
                "persist_dir": str(persist_dir),
                "error": f"필수 테이블이 없습니다: {missing}",
                "tables": tables,
            }

        cur = con.cursor()
        cur.execute("select id, name, dimension from collections where name = ?", (collection_name,))
        row = cur.fetchone()
        if not row:
            return {
                "persist_dir": str(persist_dir),
                "error": f"collections에서 찾지 못했습니다: {collection_name}",
            }

        collection_id, _, dimension = row
        segment_cols = _sqlite_columns(con, "segments")
        if "collection" in segment_cols:
            segment_fk = "collection"
        elif "collection_id" in segment_cols:
            segment_fk = "collection_id"
        else:
            return {
                "persist_dir": str(persist_dir),
                "error": "segments 테이블에서 collection FK 컬럼을 찾지 못했습니다.",
                "segments_columns": segment_cols,
            }

        cur.execute(f"select id from segments where {segment_fk} = ?", (collection_id,))
        segment_ids = [r[0] for r in cur.fetchall()]
        if not segment_ids:
            return {
                "persist_dir": str(persist_dir),
                "collection": collection_name,
                "collection_id": collection_id,
                "dimension": dimension,
                "docs": [],
                "message": "해당 컬렉션에 연결된 segments가 없습니다.",
            }

        placeholders = ",".join(["?"] * len(segment_ids))
        cur.execute(
            f"select id, embedding_id, segment_id, created_at from embeddings where segment_id in ({placeholders}) order by id desc limit ?",
            (*segment_ids, int(limit)),
        )
        embed_rows = cur.fetchall()
        embed_ids = [r[0] for r in embed_rows]
        if not embed_ids:
            return {
                "persist_dir": str(persist_dir),
                "collection": collection_name,
                "collection_id": collection_id,
                "dimension": dimension,
                "docs": [],
                "message": "embeddings가 비어있습니다.",
            }

        placeholders = ",".join(["?"] * len(embed_ids))
        cur.execute(
            f"select id, key, string_value, int_value, float_value, bool_value from embedding_metadata where id in ({placeholders})",
            tuple(embed_ids),
        )
        meta_rows = cur.fetchall()
        meta_by_id: Dict[int, Dict[str, Any]] = {}
        for mid, key, s_val, i_val, f_val, b_val in meta_rows:
            if mid not in meta_by_id:
                meta_by_id[mid] = {}
            value: Any = None
            if s_val is not None:
                value = s_val
            elif i_val is not None:
                value = i_val
            elif f_val is not None:
                value = f_val
            elif b_val is not None:
                value = bool(b_val)
            meta_by_id[mid][key] = value

        docs = []
        for rid, embedding_id, segment_id, created_at in embed_rows:
            kv = meta_by_id.get(rid, {})
            document = kv.get("chroma:document")
            metadata = {k: v for k, v in kv.items() if k != "chroma:document"}
            docs.append(
                {
                    "row_id": rid,
                    "embedding_id": embedding_id,
                    "segment_id": segment_id,
                    "created_at": created_at,
                    "document": _truncate(str(document or ""), int(max_chars)),
                    "metadata": metadata,
                }
            )

        return {
            "persist_dir": str(persist_dir),
            "collection": collection_name,
            "collection_id": collection_id,
            "dimension": dimension,
            "docs": docs,
        }
    finally:
        con.close()


def _sqlite_dump_docs(
    *,
    persist_dir: Path,
    collection_name: str,
    output: Path,
    batch_size: int,
    limit: Optional[int],
    max_chars: Optional[int],
) -> Dict[str, Any]:
    """HNSW 인덱스를 못 열어도 sqlite에서 문서/메타데이터를 JSONL로 덤프한다."""

    con = _sqlite_connect(persist_dir)
    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        tables = _sqlite_tables(con)
        tables_set = set(tables)
        required = {"collections", "segments", "embeddings", "embedding_metadata"}
        missing = sorted(required - tables_set)
        if missing:
            return {
                "persist_dir": str(persist_dir),
                "error": f"필수 테이블이 없습니다: {missing}",
                "tables": tables,
            }

        cur = con.cursor()
        cur.execute("select id, dimension from collections where name = ?", (collection_name,))
        row = cur.fetchone()
        if not row:
            return {
                "persist_dir": str(persist_dir),
                "error": f"collections에서 찾지 못했습니다: {collection_name}",
            }

        collection_id, dimension = row

        segment_cols = _sqlite_columns(con, "segments")
        if "collection" in segment_cols:
            segment_fk = "collection"
        elif "collection_id" in segment_cols:
            segment_fk = "collection_id"
        else:
            return {
                "persist_dir": str(persist_dir),
                "error": "segments 테이블에서 collection FK 컬럼을 찾지 못했습니다.",
                "segments_columns": segment_cols,
            }

        cur.execute(f"select id from segments where {segment_fk} = ?", (collection_id,))
        segment_ids = [r[0] for r in cur.fetchall()]
        if not segment_ids:
            return {
                "persist_dir": str(persist_dir),
                "collection": collection_name,
                "collection_id": collection_id,
                "dimension": dimension,
                "written_rows": 0,
                "dump_path": str(output),
                "message": "해당 컬렉션에 연결된 segments가 없습니다.",
            }

        placeholders = ",".join(["?"] * len(segment_ids))
        last_row_id = 0
        written = 0

        with output.open("w", encoding="utf-8") as f:
            while True:
                remaining = None
                if limit is not None:
                    remaining = max(0, int(limit) - written)
                    if remaining <= 0:
                        break
                current_batch = max(1, int(batch_size))
                if remaining is not None:
                    current_batch = min(current_batch, remaining)

                cur.execute(
                    f"select id, embedding_id, segment_id, created_at from embeddings where segment_id in ({placeholders}) and id > ? order by id asc limit ?",
                    (*segment_ids, int(last_row_id), int(current_batch)),
                )
                embed_rows = cur.fetchall()
                if not embed_rows:
                    break

                embed_ids = [r[0] for r in embed_rows]
                meta_placeholders = ",".join(["?"] * len(embed_ids))
                cur.execute(
                    f"select id, key, string_value, int_value, float_value, bool_value from embedding_metadata where id in ({meta_placeholders})",
                    tuple(embed_ids),
                )
                meta_rows = cur.fetchall()

                meta_by_id: Dict[int, Dict[str, Any]] = {}
                for mid, key, s_val, i_val, f_val, b_val in meta_rows:
                    if mid not in meta_by_id:
                        meta_by_id[mid] = {}
                    value: Any = None
                    if s_val is not None:
                        value = s_val
                    elif i_val is not None:
                        value = i_val
                    elif f_val is not None:
                        value = f_val
                    elif b_val is not None:
                        value = bool(b_val)
                    meta_by_id[mid][key] = value

                for rid, embedding_id, segment_id, created_at in embed_rows:
                    kv = meta_by_id.get(rid, {})
                    document = kv.get("chroma:document")
                    metadata = {k: v for k, v in kv.items() if k != "chroma:document"}
                    doc_text = str(document or "")
                    if max_chars is not None and max_chars > 0:
                        doc_text = _truncate(doc_text, int(max_chars))
                    f.write(
                        json.dumps(
                            {
                                "row_id": rid,
                                "embedding_id": embedding_id,
                                "segment_id": segment_id,
                                "created_at": created_at,
                                "document": doc_text,
                                "metadata": metadata,
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                    written += 1
                    last_row_id = max(last_row_id, int(rid))

        return {
            "status": "ok",
            "persist_dir": str(persist_dir),
            "collection": collection_name,
            "collection_id": collection_id,
            "dimension": dimension,
            "dump_path": str(output),
            "written_rows": written,
        }
    finally:
        con.close()


def cmd_sqlite(args: argparse.Namespace) -> int:
    persist_dir = Path(args.persist_dir)
    con = _sqlite_connect(persist_dir)

    try:
        tables = _sqlite_tables(con)
        if args.action == "tables":
            print(json.dumps({"persist_dir": str(persist_dir), "tables": tables}, ensure_ascii=False, indent=2))
            return 0

        if args.action == "collections":
            if "collections" not in tables:
                print(
                    json.dumps(
                        {
                            "persist_dir": str(persist_dir),
                            "error": "collections 테이블이 없습니다.",
                            "tables": tables,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 1

            cols = _sqlite_columns(con, "collections")
            cur = con.cursor()
            cur.execute("select * from collections order by name")
            rows = cur.fetchall()
            items = [dict(zip(cols, row)) for row in rows]
            print(
                json.dumps(
                    {
                        "persist_dir": str(persist_dir),
                        "table": "collections",
                        "columns": cols,
                        "rows": items,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.action == "sample":
            table = args.table
            if not table:
                raise RuntimeError("--table이 필요합니다. 예: --table embeddings")
            if table not in tables:
                print(
                    json.dumps(
                        {
                            "persist_dir": str(persist_dir),
                            "error": f"테이블을 찾지 못했습니다: {table}",
                            "tables": tables,
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 1

            cols = _sqlite_columns(con, table)
            cur = con.cursor()
            cur.execute(f"select * from {table} limit ?", (int(args.limit),))
            rows = cur.fetchall()
            items = []
            for row in rows:
                item = dict(zip(cols, row))
                for key, value in list(item.items()):
                    if isinstance(value, (bytes, bytearray)):
                        item[key] = f"<bytes len={len(value)}>"
                items.append(item)

            print(
                json.dumps(
                    {
                        "persist_dir": str(persist_dir),
                        "table": table,
                        "columns": cols,
                        "sample_size": len(items),
                        "rows": items,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.action == "docs":
            result = _sqlite_docs(
                persist_dir=Path(args.persist_dir),
                collection_name=args.collection,
                limit=int(args.limit),
                max_chars=int(args.max_chars),
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if "error" not in result else 1

        if args.action == "dump":
            limit = int(args.limit)
            effective_limit = None if limit <= 0 else limit
            max_chars = int(args.max_chars)
            effective_max_chars = None if max_chars <= 0 else max_chars
            result = _sqlite_dump_docs(
                persist_dir=Path(args.persist_dir),
                collection_name=args.collection,
                output=Path(args.output),
                batch_size=int(args.batch_size),
                limit=effective_limit,
                max_chars=effective_max_chars,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("status") == "ok" and "error" not in result else 1

        raise RuntimeError(f"지원하지 않는 action: {args.action}")
    finally:
        con.close()


def _truncate(text: str, max_chars: int) -> str:
    if text is None:
        return ""
    if max_chars <= 0:
        return text
    text = str(text)
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 1)] + "…"


def _iter_collection_get(
    collection,
    *,
    include: List[str],
    batch_size: int,
    limit: Optional[int],
) -> Iterable[Dict[str, Any]]:
    """가능하면 offset 기반으로 페이지네이션 하며 가져온다.

    Chroma 버전에 따라 offset이 없을 수 있어, 그 경우에는 limit만으로 1회 호출한다.
    """

    total = None
    try:
        total = int(collection.count())
    except Exception:
        total = None

    effective_limit = limit if (limit is not None and limit > 0) else None
    if total is not None and effective_limit is not None:
        total = min(total, effective_limit)

    # offset 지원 여부는 호출로 판별
    offset = 0
    fetched = 0
    while True:
        remaining = None
        if effective_limit is not None:
            remaining = max(0, effective_limit - fetched)
            if remaining <= 0:
                break

        current_batch = batch_size
        if remaining is not None:
            current_batch = min(current_batch, remaining)

        try:
            result = collection.get(
                include=include,
                limit=current_batch,
                offset=offset,
            )
        except TypeError:
            # offset 미지원
            result = collection.get(include=include, limit=current_batch)

        ids = result.get("ids") or []
        if not ids:
            break

        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        embeddings = result.get("embeddings") or []

        for i in range(len(ids)):
            row: Dict[str, Any] = {"id": ids[i]}
            if "documents" in include:
                row["document"] = documents[i] if i < len(documents) else None
            if "metadatas" in include:
                row["metadata"] = metadatas[i] if i < len(metadatas) else None
            if "embeddings" in include:
                row["embedding"] = embeddings[i] if i < len(embeddings) else None
            yield row

        fetched += len(ids)
        offset += len(ids)

        if total is not None and fetched >= total:
            break


def cmd_list(args: argparse.Namespace) -> int:
    chromadb = _try_import_chromadb()

    client = chromadb.PersistentClient(path=_normalize_persist_dir_for_chroma(args.persist_dir))
    collections = client.list_collections()

    if not collections:
        print("[EMPTY] collections=0")
        return 0

    print(f"collections={len(collections)}")
    for col in collections:
        name = getattr(col, "name", None) or str(col)
        print(f"- {name}")
    return 0


def cmd_count(args: argparse.Namespace) -> int:
    chromadb = _try_import_chromadb()

    client = chromadb.PersistentClient(path=_normalize_persist_dir_for_chroma(args.persist_dir))
    try:
        collection = client.get_collection(args.collection)
        print(collection.count())
    except Exception as exc:
        if _looks_like_hnsw_load_error(exc):
            raise RuntimeError(
                "HNSW 인덱스 로딩 오류로 컬렉션을 열 수 없습니다. "
                "대신 sqlite 모드로 확인하세요: python scripts/inspect_chromadb.py sqlite --action tables"
            ) from exc
        raise
    return 0


def cmd_sample(args: argparse.Namespace) -> int:
    chromadb = _try_import_chromadb()

    client = chromadb.PersistentClient(path=_normalize_persist_dir_for_chroma(args.persist_dir))
    try:
        collection = client.get_collection(args.collection)
    except Exception as exc:
        if _looks_like_hnsw_load_error(exc):
            result = _sqlite_docs(
                persist_dir=Path(args.persist_dir),
                collection_name=str(args.collection),
                limit=int(args.limit),
                max_chars=int(args.max_chars),
            )
            # Chroma 모드가 깨진 환경에서도 `sample` 명령이 샘플을 보여주도록 폴백한다.
            print(json.dumps({"mode": "sqlite_fallback", **result}, ensure_ascii=False, indent=2))
            return 0 if "error" not in result else 1
        raise

    include: List[str] = []
    if args.include_documents:
        include.append("documents")
    if args.include_metadatas:
        include.append("metadatas")
    if args.include_embeddings:
        include.append("embeddings")

    if not include:
        include = ["documents", "metadatas"]

    try:
        rows = list(
            _iter_collection_get(
                collection,
                include=include,
                batch_size=max(1, int(args.limit)),
                limit=int(args.limit),
            )
        )
    except Exception as exc:
        if _looks_like_hnsw_load_error(exc):
            result = _sqlite_docs(
                persist_dir=Path(args.persist_dir),
                collection_name=str(args.collection),
                limit=int(args.limit),
                max_chars=int(args.max_chars),
            )
            print(json.dumps({"mode": "sqlite_fallback", **result}, ensure_ascii=False, indent=2))
            return 0 if "error" not in result else 1
        raise

    print(
        json.dumps(
            {
                "persist_dir": str(args.persist_dir),
                "collection": args.collection,
                "count": int(collection.count()),
                "sample_size": len(rows),
                "rows": [
                    {
                        **({"id": row.get("id")}),
                        **(
                            {"document": _truncate(row.get("document") or "", args.max_chars)}
                            if "document" in row
                            else {}
                        ),
                        **({"metadata": row.get("metadata")} if "metadata" in row else {}),
                        **(
                            {"embedding_dim": len(row.get("embedding") or [])}
                            if "embedding" in row
                            else {}
                        ),
                    }
                    for row in rows
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_dump(args: argparse.Namespace) -> int:
    chromadb = _try_import_chromadb()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=_normalize_persist_dir_for_chroma(args.persist_dir))
    try:
        collection = client.get_collection(args.collection)
    except Exception as exc:
        if _looks_like_hnsw_load_error(exc):
            raise RuntimeError(
                "HNSW 인덱스 로딩 오류로 컬렉션을 열 수 없습니다. "
                "대신 sqlite 모드로 일부 테이블을 확인하세요: python scripts/inspect_chromadb.py sqlite --action tables"
            ) from exc
        raise

    include: List[str] = []
    if args.include_documents:
        include.append("documents")
    if args.include_metadatas:
        include.append("metadatas")
    if args.include_embeddings:
        include.append("embeddings")

    if not include:
        include = ["documents", "metadatas"]

    batch_size = max(1, int(args.batch_size))
    limit = int(args.limit) if int(args.limit) > 0 else None

    written = 0
    with output_path.open("w", encoding="utf-8") as f:
        for row in _iter_collection_get(
            collection,
            include=include,
            batch_size=batch_size,
            limit=limit,
        ):
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1

    print(
        json.dumps(
            {
                "status": "ok",
                "persist_dir": str(args.persist_dir),
                "collection": args.collection,
                "collection_count": int(collection.count()),
                "dump_path": str(output_path),
                "written_rows": written,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ChromaDB 저장 데이터 점검/덤프")
    parser.add_argument(
        "--persist-dir",
        type=str,
        default=settings.CHROMA_DB_PATH,
        help="ChromaDB persist 경로 (기본: settings.CHROMA_DB_PATH)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    p_list = subparsers.add_parser("list", help="컬렉션 목록 출력")
    p_list.set_defaults(func=cmd_list)

    p_count = subparsers.add_parser("count", help="컬렉션 문서(청크) 수 출력")
    p_count.add_argument("--collection", type=str, default="civil_cases_v1")
    p_count.set_defaults(func=cmd_count)

    p_sample = subparsers.add_parser("sample", help="샘플 레코드(JSON) 출력")
    p_sample.add_argument("--collection", type=str, default="civil_cases_v1")
    p_sample.add_argument("--limit", type=int, default=5, help="샘플 수")
    p_sample.add_argument("--max-chars", type=int, default=300, help="document 출력 최대 글자")
    p_sample.add_argument("--include-documents", action="store_true", help="documents 포함")
    p_sample.add_argument("--include-metadatas", action="store_true", help="metadatas 포함")
    p_sample.add_argument("--include-embeddings", action="store_true", help="embeddings 포함(권장X)")
    p_sample.set_defaults(func=cmd_sample)

    p_dump = subparsers.add_parser("dump", help="JSONL로 덤프 저장")
    p_dump.add_argument("--collection", type=str, default="civil_cases_v1")
    p_dump.add_argument("--output", type=str, default=str(Path("logs") / "chroma" / "dump.jsonl"))
    p_dump.add_argument("--batch-size", type=int, default=200)
    p_dump.add_argument("--limit", type=int, default=0, help="0이면 전체 덤프")
    p_dump.add_argument("--include-documents", action="store_true", help="documents 포함")
    p_dump.add_argument("--include-metadatas", action="store_true", help="metadatas 포함")
    p_dump.add_argument("--include-embeddings", action="store_true", help="embeddings 포함(권장X)")
    p_dump.set_defaults(func=cmd_dump)

    p_sqlite = subparsers.add_parser(
        "sqlite",
        help="ChromaDB sqlite 파일을 직접 조회(폴백 모드)",
    )
    p_sqlite.add_argument(
        "--action",
        type=str,
        default="tables",
        choices=["tables", "collections", "sample", "docs", "dump"],
        help="tables: 테이블 목록 / collections: collections 테이블 / sample: 특정 테이블 샘플 / docs: 문서 샘플 / dump: 문서 전체 덤프",
    )
    p_sqlite.add_argument("--table", type=str, default="", help="action=sample일 때 조회할 테이블")
    p_sqlite.add_argument("--limit", type=int, default=10, help="sample 행 수")
    p_sqlite.add_argument("--collection", type=str, default="civil_cases_v1", help="action=docs일 때 컬렉션 이름")
    p_sqlite.add_argument("--max-chars", type=int, default=300, help="action=docs일 때 document 출력 최대 글자")
    p_sqlite.add_argument(
        "--output",
        type=str,
        default=str(Path("logs") / "chroma" / "civil_cases_v1.sqlite_dump.jsonl"),
        help="action=dump일 때 JSONL 출력 경로",
    )
    p_sqlite.add_argument("--batch-size", type=int, default=500, help="action=dump 배치 크기")
    p_sqlite.set_defaults(func=cmd_sqlite)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    persist_dir = Path(args.persist_dir)
    persist_dir.mkdir(parents=True, exist_ok=True)

    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
