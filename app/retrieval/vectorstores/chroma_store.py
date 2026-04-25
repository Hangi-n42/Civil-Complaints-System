"""ChromaDB-backed retrieval storage and query helper."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from app.core.title_builder import build_case_title


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _split_entity_labels(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [item for item in value.split("|") if item]
    else:
        raw_items = []

    labels: List[str] = []
    seen = set()
    for item in raw_items:
        label = str(item).strip().upper()
        if not label or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def _to_iso_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone(timedelta(hours=9)))
        return parsed
    except ValueError:
        return None


def _to_timestamp(value: Any) -> int:
    parsed = _to_iso_datetime(value)
    if parsed is None:
        return 0
    return int(parsed.timestamp())


class ChromaVectorStore:
    """Thin adapter around ChromaDB for retrieval indexing and search."""

    def __init__(self, persist_directory: str, embedding_model_name: str, embedding_device: str) -> None:
        self.persist_directory = Path(persist_directory)
        self.embedding_model_name = embedding_model_name
        self.embedding_device = embedding_device
        self._client = None
        self._embedding_model = None
        self._collections: Dict[str, Any] = {}

    def _get_client(self):
        if self._client is None:
            import chromadb

            self.persist_directory.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self.persist_directory))
        return self._client

    def _get_embedding_model(self):
        if self._embedding_model is None:
            from sentence_transformers import SentenceTransformer

            self._embedding_model = SentenceTransformer(
                self.embedding_model_name,
                device=self.embedding_device,
            )
        return self._embedding_model

    def _get_collection(self, collection_name: str):
        key = collection_name.strip() if collection_name else "civil_cases_v1"
        if key not in self._collections:
            client = self._get_client()
            self._collections[key] = client.get_or_create_collection(
                name=key,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collections[key]

    def reset_collection(self, collection_name: str) -> None:
        key = collection_name.strip() if collection_name else "civil_cases_v1"
        client = self._get_client()
        try:
            client.delete_collection(key)
        except Exception:
            pass
        self._collections.pop(key, None)

    def count(self, collection_name: str) -> int:
        collection = self._get_collection(collection_name)
        return int(collection.count())

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        model = self._get_embedding_model()
        vectors = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        if hasattr(vectors, "tolist"):
            return vectors.tolist()
        return [list(vector) for vector in vectors]

    def _build_unique_id(self, record: Dict[str, Any]) -> str:
        doc_id = str(record.get("doc_id") or record.get("case_id") or "doc").strip()
        chunk_id = str(record.get("chunk_id") or "chunk").strip()
        return f"{doc_id}::{chunk_id}"

    def _build_metadata(self, record: Dict[str, Any]) -> Dict[str, Any]:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
        summary = record.get("summary") if isinstance(record.get("summary"), dict) else {}
        labels = record.get("entity_labels") or []

        try:
            chunk_index = int(record.get("chunk_index", 0))
        except (TypeError, ValueError):
            chunk_index = 0

        created_at = str(record.get("created_at") or "")
        created_at_ts = _to_timestamp(created_at)

        return {
            "doc_id": str(record.get("doc_id") or record.get("case_id") or ""),
            "chunk_id": str(record.get("chunk_id") or ""),
            "case_id": str(record.get("case_id") or ""),
            "chunk_index": chunk_index,
            "source": str(record.get("source") or "unknown"),
            "created_at": created_at,
            "created_at_ts": created_at_ts,
            "category": str(record.get("category") or ""),
            "region": str(record.get("region") or ""),
            "entity_labels": "|".join(str(label).strip().upper() for label in labels if str(label).strip()),
            "title": str(record.get("title") or ""),
            "summary_observation": _normalize_text(summary.get("observation")),
            "summary_request": _normalize_text(summary.get("request")),
            "pipeline_version": str(metadata.get("pipeline_version") or "week2"),
            "structuring_confidence": float(metadata.get("structuring_confidence") or 0.0),
            "content_type": str(metadata.get("content_type") or "full"),
        }

    def upsert_records(self, collection_name: str, records: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        collection = self._get_collection(collection_name)
        normalized_records = [record for record in records if isinstance(record, dict)]
        if not normalized_records:
            return {
                "indexed_count": 0,
                "chunk_count": 0,
                "records": [],
            }

        documents = [str(record.get("chunk_text") or "") for record in normalized_records]
        embeddings = self.embed_texts(documents)
        ids = [self._build_unique_id(record) for record in normalized_records]
        metadatas = [self._build_metadata(record) for record in normalized_records]

        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        return {
            "indexed_count": len(normalized_records),
            "chunk_count": len(normalized_records),
            "records": [
                {
                    "case_id": str(record.get("case_id") or ""),
                    "chunk_ids": [str(record.get("chunk_id") or "")],
                }
                for record in normalized_records
            ],
        }

    def query(
        self,
        *,
        collection_name: str,
        query: str,
        top_k: int,
        filters: Optional[Dict[str, Any]] = None,
        threshold: float = 0.0,
        snippet_max_chars: int = 140,
    ) -> List[Dict[str, Any]]:
        collection = self._get_collection(collection_name)
        candidate_count = max(1, min(50, max(top_k, top_k * 5)))
        query_vector = self.embed_texts([query])[0]

        where: Dict[str, Any] = {}
        normalized_filters = filters or {}
        category = normalized_filters.get("category")
        if category:
            where["category"] = str(category)
        created_at = normalized_filters.get("created_at")
        if created_at:
            where["created_at"] = str(created_at)

        date_from = _to_iso_datetime(normalized_filters.get("date_from"))
        date_to = _to_iso_datetime(normalized_filters.get("date_to"))
        if date_from or date_to:
            created_at_ts: Dict[str, Any] = {}
            if date_from:
                created_at_ts["$gte"] = int(date_from.timestamp())
            if date_to:
                created_at_ts["$lte"] = int(date_to.timestamp())
            if created_at_ts:
                where["created_at_ts"] = created_at_ts

        query_kwargs: Dict[str, Any] = {
            "query_embeddings": [query_vector],
            "n_results": candidate_count,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            query_kwargs["where"] = where

        results = collection.query(**query_kwargs)
        ids = (results.get("ids") or [[]])[0]
        documents = (results.get("documents") or [[]])[0]
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]

        scored: List[Dict[str, Any]] = []
        for index, (storage_id, document, metadata, distance) in enumerate(
            zip(ids, documents, metadatas, distances),
            start=1,
        ):
            metadata = metadata or {}
            doc_text = str(document or "")
            chunk_id = str(metadata.get("chunk_id") or "")
            case_id = str(metadata.get("case_id") or "")
            region = str(metadata.get("region") or "")
            category = str(metadata.get("category") or "")
            entity_labels = _split_entity_labels(metadata.get("entity_labels"))
            created_at = str(metadata.get("created_at") or "")
            created_at_ts = metadata.get("created_at_ts")

            if normalized_filters.get("region"):
                if str(normalized_filters["region"]) not in region:
                    continue
            if normalized_filters.get("entity_labels"):
                wanted = {str(label).strip().upper() for label in normalized_filters["entity_labels"] if str(label).strip()}
                if wanted and not wanted.intersection(entity_labels):
                    continue

            parsed_created_at = _to_iso_datetime(created_at)
            if normalized_filters.get("date_from") and parsed_created_at is not None:
                if parsed_created_at < _to_iso_datetime(normalized_filters.get("date_from")):
                    continue
            if normalized_filters.get("date_to") and parsed_created_at is not None:
                if parsed_created_at > _to_iso_datetime(normalized_filters.get("date_to")):
                    continue

            similarity = 1.0 - float(distance or 0.0)
            if similarity < threshold:
                continue

            summary = {
                "observation": str(metadata.get("summary_observation") or ""),
                "request": str(metadata.get("summary_request") or ""),
            }
            title = str(metadata.get("title") or "")
            if not title:
                title = build_case_title(
                    observation=summary.get("observation"),
                    request=summary.get("request"),
                    chunk_text=doc_text,
                    category=category or None,
                )

            scored.append(
                {
                    "storage_id": storage_id,
                    "doc_id": str(metadata.get("doc_id") or case_id or storage_id),
                    "score": round(max(0.0, similarity), 2),
                    "chunk_id": chunk_id,
                    "case_id": case_id,
                    "title": title,
                    "snippet": self._build_snippet(doc_text, max_length=snippet_max_chars),
                    "summary": summary,
                    "metadata": {
                        "created_at": created_at,
                        "category": category,
                        "region": region,
                        "entity_labels": entity_labels,
                        "created_at_ts": int(created_at_ts or 0),
                    },
                }
            )

        scored.sort(key=lambda item: item["score"], reverse=True)
        results_list = scored[: max(1, top_k)]
        for rank, item in enumerate(results_list, start=1):
            item["rank"] = rank
        return results_list

    def _build_snippet(self, chunk_text: str, max_length: int = 120) -> str:
        text = " ".join(chunk_text.split())
        if len(text) <= max_length:
            return text
        return text[:max_length].rstrip() + "..."
