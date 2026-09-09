"""向量存储实现：Qdrant 本地持久化模式"""

import os
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import Distance, VectorParams, PointStruct

from .base import BaseVectorStore, Chunk


class QdrantVectorStore(BaseVectorStore):
    """
    Qdrant 向量存储（本地持久化模式，无需单独服务）

    使用 QdrantClient(path=...) 将数据持久化到本地磁盘。
    """

    def __init__(
        self,
        collection_name: str | None = None,
        vector_size: int = 768,
        path: str | None = None,
    ):
        self.collection_name = collection_name or os.getenv(
            "RAG_COLLECTION_NAME", "agentlab_knowledge"
        )
        self.vector_size = vector_size
        self.path = path or os.getenv("RAG_VECTOR_DB_PATH", "./data/qdrant")

        # 本地持久化模式
        self.client = QdrantClient(path=self.path)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """确保集合存在（不存在则创建）"""
        collections = self.client.get_collections().collections
        exists = any(c.name == self.collection_name for c in collections)

        if not exists:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE,
                ),
            )
        else:
            # 验证向量维度一致
            info = self.client.get_collection(self.collection_name)
            config = info.config.params.vectors
            if isinstance(config, dict):
                actual_size = config.get("size")
            else:
                actual_size = getattr(config, "size", None)
            if actual_size and actual_size != self.vector_size:
                raise ValueError(
                    f"集合 {self.collection_name} 维度为 {actual_size}，"
                    f"与配置的 {self.vector_size} 不一致。请删除旧数据后重建。"
                )

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """写入切块及其向量"""
        if not chunks:
            return

        points = [
            PointStruct(
                id=chunk.chunk_id,
                vector=embedding,
                payload={
                    "source": chunk.source,
                    "content": chunk.content,
                    "chunk_index": chunk.chunk_index,
                    "metadata": chunk.metadata,
                },
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]

        # upsert：存在则更新，不存在则插入
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

    def search(
        self, query_embedding: list[float], top_k: int = 4
    ) -> list[tuple[Chunk, float]]:
        """相似度检索，返回 (chunk, score) 列表"""
        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=top_k,
            with_payload=True,
        )

        chunks: list[tuple[Chunk, float]] = []
        for point in results.points:
            payload: dict[str, Any] = point.payload or {}
            chunk = Chunk(
                chunk_id=str(point.id),
                source=payload.get("source", ""),
                content=payload.get("content", ""),
                chunk_index=payload.get("chunk_index", 0),
                metadata=payload.get("metadata", {}),
            )
            chunks.append((chunk, point.score))

        return chunks

    def count(self) -> int:
        """返回集合中的向量数量"""
        result = self.client.count(
            collection_name=self.collection_name, exact=True
        )
        return result.count

    def clear(self) -> None:
        """清空集合（用于重建索引）"""
        self.client.delete_collection(self.collection_name)
        self._ensure_collection()
