"""HNSW 인덱스 로딩 오류(Error loading hnsw index) 복구 스크립트.

배경:
- ChromaDB persistent DB는 sqlite + segment 디렉터리(HNSW index 파일들)로 구성됩니다.
- segment의 HNSW index가 깨지거나 누락되면 `collection.count()/get()/query()`에서
  `Error loading hnsw index`가 발생할 수 있습니다.

해결 전략(가장 안전/확실):
1) source sqlite(`chroma.sqlite3`)에서 문서(`chroma:document`)와 메타데이터를 읽는다.
2) 임베딩을 다시 생성한다(sentence-transformers).
3) target persist 디렉터리에 새 컬렉션을 생성하고 upsert한다.

주의:
- 이 스크립트는 HNSW index 파일을 "수리"하기보다 "재생성"합니다.
- 데이터를 보존하려면 source persist 디렉터리는 그대로 두고 target을 다른 폴더로 지정하세요.
- 임베딩 모델 다운로드가 필요할 수 있습니다.

예시:
  # 1) 작은 샘플로 복구 가능성 검증
  python scripts/repair_chromadb_hnsw.py --limit 50 --device cpu

  # 2) 전체 복구(새 폴더에 생성)
  python scripts/repair_chromadb_hnsw.py --limit 0 --device cpu \
    --target-persist-dir data/chroma_db_rebuilt \
    --target-collection civil_cases_v1

  # 3) 복구 후, 앱에서 target 경로를 쓰도록 변경
  #    (예: CHROMA_DB_PATH=data/chroma_db_rebuilt)
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings


def _connect_sqlite(persist_dir: Path) -> sqlite3.Connection:
    db_path = persist_dir / "chroma.sqlite3"
    if not db_path.exists():
        raise RuntimeError(f"sqlite 파일을 찾지 못했습니다: {db_path}")
    return sqlite3.connect(str(db_path))


def _sqlite_columns(con: sqlite3.Connection, table: str) -> List[str]:
    cur = con.cursor()
    cur.execute(f"pragma table_info({table})")
    return [row[1] for row in cur.fetchall()]


def _get_collection_id(con: sqlite3.Connection, collection_name: str) -> Tuple[str, int]:
    cur = con.cursor()
    cur.execute("select id, dimension from collections where name = ?", (collection_name,))
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"collections에서 찾지 못했습니다: {collection_name}")
    return str(row[0]), int(row[1])


def _get_segment_ids(con: sqlite3.Connection, collection_id: str) -> List[str]:
    cols = _sqlite_columns(con, "segments")
    if "collection" in cols:
        fk = "collection"
    elif "collection_id" in cols:
        fk = "collection_id"
    else:
        raise RuntimeError(f"segments 테이블에서 collection FK 컬럼을 찾지 못했습니다. cols={cols}")

    cur = con.cursor()
    cur.execute(f"select id from segments where {fk} = ?", (collection_id,))
    return [str(row[0]) for row in cur.fetchall()]


def _iter_embedding_rows(
    con: sqlite3.Connection,
    *,
    segment_ids: List[str],
    batch_size: int,
    limit: Optional[int],
) -> Iterable[List[Tuple[int, str, str, str]]]:
    """embeddings 테이블에서 (row_id, embedding_id, segment_id, created_at)을 배치로 반환."""

    if not segment_ids:
        return

    placeholders = ",".join(["?"] * len(segment_ids))
    last_row_id = 0
    fetched = 0

    while True:
        remaining = None
        if limit is not None:
            remaining = max(0, int(limit) - fetched)
            if remaining <= 0:
                break

        current_batch = max(1, int(batch_size))
        if remaining is not None:
            current_batch = min(current_batch, remaining)

        cur = con.cursor()
        cur.execute(
            f"select id, embedding_id, segment_id, created_at from embeddings where segment_id in ({placeholders}) and id > ? order by id asc limit ?",
            (*segment_ids, int(last_row_id), int(current_batch)),
        )
        rows = cur.fetchall()
        if not rows:
            break

        batch: List[Tuple[int, str, str, str]] = []
        for rid, embedding_id, segment_id, created_at in rows:
            batch.append((int(rid), str(embedding_id), str(segment_id), str(created_at)))
            last_row_id = max(last_row_id, int(rid))

        fetched += len(batch)
        yield batch


def _load_metadata_for_ids(con: sqlite3.Connection, row_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    if not row_ids:
        return {}

    placeholders = ",".join(["?"] * len(row_ids))
    cur = con.cursor()
    cur.execute(
        f"select id, key, string_value, int_value, float_value, bool_value from embedding_metadata where id in ({placeholders})",
        tuple(row_ids),
    )
    rows = cur.fetchall()

    meta_by_id: Dict[int, Dict[str, Any]] = {}
    for rid, key, s_val, i_val, f_val, b_val in rows:
        rid = int(rid)
        if rid not in meta_by_id:
            meta_by_id[rid] = {}

        value: Any = None
        if s_val is not None:
            value = s_val
        elif i_val is not None:
            value = i_val
        elif f_val is not None:
            value = f_val
        elif b_val is not None:
            value = bool(b_val)

        meta_by_id[rid][str(key)] = value

    return meta_by_id


def _get_st_model(model_name: str, device: str):
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name, device=device)


def _encode_with_retry(model, texts: List[str], *, batch_size: int) -> List[List[float]]:
    current_batch = max(1, int(batch_size))
    retries = 0

    while True:
        try:
            vectors = model.encode(
                texts,
                batch_size=current_batch,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            if hasattr(vectors, "tolist"):
                return vectors.tolist()
            return [list(vec) for vec in vectors]
        except RuntimeError as exc:
            msg = str(exc).lower()
            if "out of memory" not in msg or current_batch == 1 or retries >= 3:
                raise
            retries += 1
            current_batch = max(1, current_batch // 2)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ChromaDB HNSW 인덱스 오류 복구(재생성)")
    parser.add_argument(
        "--source-persist-dir",
        type=str,
        default=settings.CHROMA_DB_PATH,
        help="원본 ChromaDB persist 경로",
    )
    parser.add_argument(
        "--source-collection",
        type=str,
        default="civil_cases_v1",
        help="원본 컬렉션 이름",
    )
    parser.add_argument(
        "--target-persist-dir",
        type=str,
        default=str(Path("data") / "chroma_db_rebuilt"),
        help="복구 결과를 저장할 persist 경로(권장: 새 폴더)",
    )
    parser.add_argument(
        "--target-collection",
        type=str,
        default="civil_cases_v1",
        help="target 컬렉션 이름",
    )
    parser.add_argument(
        "--reset-target",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="True(기본): target 컬렉션 삭제 후 재생성",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="처리할 최대 row 수 (0: 전체)",
    )
    parser.add_argument(
        "--read-batch-size",
        type=int,
        default=500,
        help="sqlite에서 읽는 배치 크기",
    )
    parser.add_argument(
        "--embed-batch-size",
        type=int,
        default=64,
        help="임베딩 배치 크기(메모리 부족 시 자동 감소)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=settings.EMBEDDING_MODEL,
        help="sentence-transformers 모델 이름",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=settings.EMBEDDING_DEVICE,
        help="임베딩 디바이스(cpu/cuda)",
    )
    args = parser.parse_args(argv)

    source_dir = Path(args.source_persist_dir)
    target_dir = Path(args.target_persist_dir)
    source_collection = str(args.source_collection)
    target_collection = str(args.target_collection)

    limit = int(args.limit)
    effective_limit = None if limit <= 0 else limit

    import chromadb

    con = _connect_sqlite(source_dir)
    try:
        collection_id, dimension = _get_collection_id(con, source_collection)
        segment_ids = _get_segment_ids(con, collection_id)
        if not segment_ids:
            raise RuntimeError(f"source 컬렉션에 연결된 segment가 없습니다: {source_collection}")

        target_dir.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(target_dir))

        if args.reset_target:
            try:
                client.delete_collection(target_collection)
            except Exception:
                pass

        collection = client.get_or_create_collection(
            name=target_collection,
            metadata={"hnsw:space": "cosine"},
        )

        model = _get_st_model(str(args.model), str(args.device))

        total_written = 0
        started_at = datetime.now().isoformat(timespec="seconds")
        print(
            json.dumps(
                {
                    "status": "start",
                    "started_at": started_at,
                    "source_persist_dir": str(source_dir),
                    "source_collection": source_collection,
                    "collection_id": collection_id,
                    "dimension": dimension,
                    "target_persist_dir": str(target_dir),
                    "target_collection": target_collection,
                    "model": str(args.model),
                    "device": str(args.device),
                    "limit": effective_limit or 0,
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        for batch in _iter_embedding_rows(
            con,
            segment_ids=segment_ids,
            batch_size=int(args.read_batch_size),
            limit=effective_limit,
        ):
            row_ids = [rid for rid, _, _, _ in batch]
            meta_by_id = _load_metadata_for_ids(con, row_ids)

            ids: List[str] = []
            documents: List[str] = []
            metadatas: List[Dict[str, Any]] = []

            for rid, embedding_id, _, _ in batch:
                kv = meta_by_id.get(rid, {})
                doc = str(kv.get("chroma:document") or "")
                metadata = {k: v for k, v in kv.items() if k != "chroma:document"}

                if not doc.strip():
                    continue

                ids.append(embedding_id)
                documents.append(doc)
                metadatas.append(metadata)

            if not ids:
                continue

            embeddings = _encode_with_retry(model, documents, batch_size=int(args.embed_batch_size))
            collection.upsert(
                ids=ids,
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
            )

            total_written += len(ids)
            if total_written % 2000 < len(ids):
                print(json.dumps({"status": "progress", "written": total_written}, ensure_ascii=False))

        finished_at = datetime.now().isoformat(timespec="seconds")
        print(
            json.dumps(
                {
                    "status": "ok",
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "written_rows": total_written,
                    "target_persist_dir": str(target_dir),
                    "target_collection": target_collection,
                    "target_count": int(collection.count()),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
