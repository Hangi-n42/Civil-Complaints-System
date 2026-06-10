"""Export a ChromaDB collection with embeddings for offline transfer."""

from __future__ import annotations

import argparse
import gzip
import pickle
from pathlib import Path
from typing import Any

import chromadb
import numpy as np


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ChromaDB collection export")
    parser.add_argument("--persist-dir", default="data/chroma_db")
    parser.add_argument("--collection", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--batch-size", type=int, default=256)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    client = chromadb.PersistentClient(path=args.persist_dir)
    collection = client.get_collection(args.collection)
    total = int(collection.count())

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict[str, Any]] = []
    embeddings: list[list[float]] = []

    for offset in range(0, total, max(1, args.batch_size)):
        batch = collection.get(
            limit=max(1, args.batch_size),
            offset=offset,
            include=["documents", "metadatas", "embeddings"],
        )
        batch_ids = batch.get("ids")
        batch_documents = batch.get("documents")
        batch_metadatas = batch.get("metadatas")
        batch_embeddings = batch.get("embeddings")
        ids.extend(batch_ids if batch_ids is not None else [])
        documents.extend(batch_documents if batch_documents is not None else [])
        metadatas.extend(batch_metadatas if batch_metadatas is not None else [])
        if batch_embeddings is not None:
            embeddings.extend(batch_embeddings)
        print(f"[export] {len(ids)}/{total}")

    payload = {
        "collection_name": args.collection,
        "total": total,
        "ids": ids,
        "documents": documents,
        "metadatas": metadatas,
        "embeddings": np.asarray(embeddings, dtype=np.float32),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(args.out, "wb") as handle:
        pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)

    print(
        "[done] "
        f"collection={args.collection} ids={len(ids)} "
        f"embeddings_shape={payload['embeddings'].shape} out={args.out}"
    )


if __name__ == "__main__":
    main()
