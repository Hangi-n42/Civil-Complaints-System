"""Import an exported ChromaDB collection without recomputing embeddings."""

from __future__ import annotations

import argparse
import gzip
import pickle
from pathlib import Path
from typing import Any

import chromadb


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ChromaDB collection import")
    parser.add_argument("--persist-dir", default="data/chroma_db")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--collection", default="")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def _load_payload(path: Path) -> dict[str, Any]:
    with gzip.open(path, "rb") as handle:
        payload = pickle.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("export payload must be a dict")
    for key in ("collection_name", "ids", "documents", "metadatas", "embeddings"):
        if key not in payload:
            raise ValueError(f"missing export payload key: {key}")
    return payload


def main() -> None:
    args = _parse_args()
    payload = _load_payload(args.input)
    collection_name = args.collection.strip() or str(payload["collection_name"])

    ids = list(payload["ids"])
    documents = list(payload["documents"])
    metadatas = list(payload["metadatas"])
    embeddings = payload["embeddings"]

    if not (len(ids) == len(documents) == len(metadatas) == len(embeddings)):
        raise ValueError(
            "payload lengths differ: "
            f"ids={len(ids)} documents={len(documents)} "
            f"metadatas={len(metadatas)} embeddings={len(embeddings)}"
        )

    client = chromadb.PersistentClient(path=args.persist_dir)
    if args.replace:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    total = len(ids)
    batch_size = max(1, args.batch_size)
    for start in range(0, total, batch_size):
        end = min(total, start + batch_size)
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
            embeddings=embeddings[start:end].tolist(),
        )
        print(f"[import] {end}/{total}")

    print(f"[done] collection={collection_name} count={collection.count()}")


if __name__ == "__main__":
    main()
