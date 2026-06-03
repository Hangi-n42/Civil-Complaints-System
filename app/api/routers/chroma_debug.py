"""ChromaDB 내용을 FastAPI로 확인하기 위한 디버그 라우터.

주의:
- 운영/배포 환경에서는 노출 범위를 제한하는 것이 안전합니다.
- 현재는 로컬 개발/디버깅 용도로, 저장된 문서/메타데이터를 확인하기 위한 read-only API입니다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Query

from app.api.error_utils import error_response, make_request_id, now_iso
from app.core.config import settings

router = APIRouter(prefix="/api/v1/chroma", tags=["chroma-debug"])


def _looks_like_hnsw_load_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "hnsw" in message and "error" in message and "load" in message


def _sqlite_connect(persist_dir: Path) -> sqlite3.Connection:
    db_path = persist_dir / "chroma.sqlite3"
    if not db_path.exists():
        raise RuntimeError(f"sqlite 파일을 찾지 못했습니다: {db_path}")
    return sqlite3.connect(str(db_path))


def _sqlite_columns(con: sqlite3.Connection, table: str) -> List[str]:
    cur = con.cursor()
    cur.execute(f"pragma table_info({table})")
    return [row[1] for row in cur.fetchall()]


def _sqlite_list_collections(persist_dir: Path) -> List[Dict[str, Any]]:
    con = _sqlite_connect(persist_dir)
    try:
        cur = con.cursor()
        cur.execute("select name, dimension from collections order by name")
        rows = cur.fetchall()
        return [{"name": str(name), "dimension": int(dim)} for name, dim in rows]
    finally:
        con.close()


def _sqlite_sample_docs(
    *,
    persist_dir: Path,
    collection_name: str,
    limit: int,
    max_chars: int,
) -> Dict[str, Any]:
    con = _sqlite_connect(persist_dir)
    try:
        cur = con.cursor()
        cur.execute("select id, dimension from collections where name = ?", (collection_name,))
        row = cur.fetchone()
        if not row:
            return {"error": f"collections에서 찾지 못했습니다: {collection_name}"}

        collection_id, dimension = row

        segment_cols = _sqlite_columns(con, "segments")
        if "collection" in segment_cols:
            segment_fk = "collection"
        elif "collection_id" in segment_cols:
            segment_fk = "collection_id"
        else:
            return {
                "error": "segments 테이블에서 collection FK 컬럼을 찾지 못했습니다.",
                "segments_columns": segment_cols,
            }

        cur.execute(f"select id from segments where {segment_fk} = ?", (collection_id,))
        segment_ids = [r[0] for r in cur.fetchall()]
        if not segment_ids:
            return {
                "collection": collection_name,
                "collection_id": str(collection_id),
                "dimension": int(dimension),
                "rows": [],
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
                "collection": collection_name,
                "collection_id": str(collection_id),
                "dimension": int(dimension),
                "rows": [],
            }

        placeholders = ",".join(["?"] * len(embed_ids))
        cur.execute(
            f"select id, key, string_value, int_value, float_value, bool_value from embedding_metadata where id in ({placeholders})",
            tuple(embed_ids),
        )
        meta_rows = cur.fetchall()
        meta_by_id: Dict[int, Dict[str, Any]] = {}
        for mid, key, s_val, i_val, f_val, b_val in meta_rows:
            mid = int(mid)
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
            meta_by_id[mid][str(key)] = value

        rows: List[Dict[str, Any]] = []
        for rid, embedding_id, segment_id, created_at in embed_rows:
            rid = int(rid)
            kv = meta_by_id.get(rid, {})
            doc = str(kv.get("chroma:document") or "")
            if max_chars > 0 and len(doc) > max_chars:
                doc = doc[: max(0, max_chars - 1)] + "…"
            metadata = {k: v for k, v in kv.items() if k != "chroma:document"}
            rows.append(
                {
                    "row_id": rid,
                    "id": str(embedding_id),
                    "segment_id": str(segment_id),
                    "created_at": str(created_at),
                    "document": doc,
                    "metadata": metadata,
                }
            )

        return {
            "collection": collection_name,
            "collection_id": str(collection_id),
            "dimension": int(dimension),
            "sample_size": len(rows),
            "rows": rows,
        }
    finally:
        con.close()


@router.get("/collections")
async def list_collections() -> Dict[str, Any]:
    """persist에 존재하는 컬렉션 목록을 반환한다."""
    request_id = make_request_id()
    persist_dir = Path(settings.CHROMA_DB_PATH)

    try:
        cols = _sqlite_list_collections(persist_dir)
    except Exception as exc:
        return error_response(
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            message="ChromaDB 컬렉션 목록 조회 중 오류가 발생했습니다.",
            retryable=False,
            details={"persist_dir": str(persist_dir), "reason": str(exc)},
        )

    return {
        "success": True,
        "request_id": request_id,
        "timestamp": now_iso(),
        "data": {
            "persist_dir": str(persist_dir),
            "count": len(cols),
            "collections": cols,
        },
    }


@router.get("/collections/{collection_name}/count")
async def get_collection_count(collection_name: str) -> Dict[str, Any]:
    """컬렉션 count를 반환한다(HNSW 오류 시 오류 래핑)."""
    request_id = make_request_id()
    persist_dir = Path(settings.CHROMA_DB_PATH)

    try:
        import chromadb  # type: ignore

        client = chromadb.PersistentClient(path=str(persist_dir))
        collection = client.get_collection(collection_name)
        count = int(collection.count())
    except Exception as exc:
        if _looks_like_hnsw_load_error(exc):
            return error_response(
                request_id=request_id,
                error_code="PROCESSING_ERROR",
                message="HNSW 인덱스 로딩 오류로 count를 가져올 수 없습니다.",
                retryable=False,
                details={"persist_dir": str(persist_dir), "collection": collection_name, "reason": str(exc)},
            )
        return error_response(
            request_id=request_id,
            error_code="INTERNAL_SERVER_ERROR",
            message="ChromaDB count 조회 중 오류가 발생했습니다.",
            retryable=False,
            details={"persist_dir": str(persist_dir), "collection": collection_name, "reason": str(exc)},
        )

    return {
        "success": True,
        "request_id": request_id,
        "timestamp": now_iso(),
        "data": {
            "persist_dir": str(persist_dir),
            "collection": collection_name,
            "count": count,
        },
    }


@router.get("/collections/{collection_name}/sample")
async def sample_collection(
    collection_name: str,
    limit: int = Query(default=5, ge=1, le=50),
    max_chars: int = Query(default=300, ge=0, le=5000),
) -> Dict[str, Any]:
    """컬렉션에서 문서/메타데이터 샘플을 반환한다.

    - 정상: Chroma get() 사용
    - HNSW 오류: sqlite 폴백으로 문서/메타데이터를 조회
    """

    request_id = make_request_id()
    persist_dir = Path(settings.CHROMA_DB_PATH)

    try:
        import chromadb  # type: ignore

        client = chromadb.PersistentClient(path=str(persist_dir))
        collection = client.get_collection(collection_name)
        result = collection.get(limit=int(limit), include=["documents", "metadatas"])
        ids = result.get("ids") or []
        docs = result.get("documents") or []
        metas = result.get("metadatas") or []

        rows = []
        for i in range(len(ids)):
            doc = str(docs[i] or "") if i < len(docs) else ""
            if max_chars > 0 and len(doc) > max_chars:
                doc = doc[: max(0, max_chars - 1)] + "…"
            rows.append(
                {
                    "id": str(ids[i]),
                    "document": doc,
                    "metadata": metas[i] if i < len(metas) else None,
                }
            )

        return {
            "success": True,
            "request_id": request_id,
            "timestamp": now_iso(),
            "data": {
                "mode": "chroma",
                "persist_dir": str(persist_dir),
                "collection": collection_name,
                "sample_size": len(rows),
                "rows": rows,
            },
        }
    except Exception as exc:
        if not _looks_like_hnsw_load_error(exc):
            return error_response(
                request_id=request_id,
                error_code="INTERNAL_SERVER_ERROR",
                message="ChromaDB 샘플 조회 중 오류가 발생했습니다.",
                retryable=False,
                details={"persist_dir": str(persist_dir), "collection": collection_name, "reason": str(exc)},
            )

        # sqlite fallback
        try:
            payload = _sqlite_sample_docs(
                persist_dir=persist_dir,
                collection_name=collection_name,
                limit=int(limit),
                max_chars=int(max_chars),
            )
        except Exception as sqlite_exc:
            return error_response(
                request_id=request_id,
                error_code="PROCESSING_ERROR",
                message="HNSW 오류 + sqlite 폴백 조회에도 실패했습니다.",
                retryable=False,
                details={
                    "persist_dir": str(persist_dir),
                    "collection": collection_name,
                    "hnsw_reason": str(exc),
                    "sqlite_reason": str(sqlite_exc),
                },
            )

        if "error" in payload:
            return error_response(
                request_id=request_id,
                error_code="PROCESSING_ERROR",
                message="HNSW 오류로 sqlite 폴백 조회 중 오류가 발생했습니다.",
                retryable=False,
                details={"persist_dir": str(persist_dir), "collection": collection_name, **payload},
            )

        return {
            "success": True,
            "request_id": request_id,
            "timestamp": now_iso(),
            "data": {
                "mode": "sqlite_fallback",
                "persist_dir": str(persist_dir),
                **payload,
            },
        }
