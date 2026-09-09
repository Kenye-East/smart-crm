"""RAG 管线：索引与查询的编排入口"""

import os

from .base import BaseEmbedding, BaseVectorStore, Chunk, Document
from .document_loader import load_documents
from .embedding import BGESentenceEmbedding
from .splitter import RecursiveCharacterTextSplitter
from .vector_store import QdrantVectorStore


class RAGPipeline:
    """
    RAG 管线

    职责：编排离线索引和在线查询两条链路。
    """

    def __init__(
        self,
        embedding: BaseEmbedding | None = None,
        vector_store: BaseVectorStore | None = None,
        chunk_size: int | None = None,
        chunk_overlap: int | None = None,
        top_k: int | None = None,
    ):
        self.chunk_size = chunk_size or int(os.getenv("RAG_CHUNK_SIZE", "512"))
        self.chunk_overlap = chunk_overlap or int(
            os.getenv("RAG_CHUNK_OVERLAP", "64")
        )
        self.top_k = top_k or int(os.getenv("RAG_TOP_K", "4"))

        # 初始化组件
        self.embedding = embedding or BGESentenceEmbedding()
        # 向量库需要知道维度，先获取 embedding 维度
        self.vector_store = vector_store or QdrantVectorStore(
            vector_size=self.embedding.dimension
        )
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
        )

    def index(self, directory: str) -> dict:
        """
        离线索引：加载文档 → 切分 → 向量化 → 存储

        Args:
            directory: 文档目录

        Returns:
            索引统计信息
        """
        # 1. 加载文档
        documents = load_documents(directory)
        if not documents:
            return {"documents": 0, "chunks": 0, "status": "no_documents"}

        # 2. 切分
        chunks = self.splitter.split_documents(documents)

        # 3. 向量化（批量）
        texts = [c.content for c in chunks]
        embeddings = self.embedding.embed(texts, is_query=False)

        # 4. 存储（先清空旧索引，保证幂等）
        self.vector_store.clear()
        self.vector_store.add(chunks, embeddings)

        return {
            "documents": len(documents),
            "chunks": len(chunks),
            "status": "ok",
        }

    def query(self, question: str) -> dict:
        """
        在线查询：向量化问题 → 检索 → 返回相关切块

        Args:
            question: 用户问题

        Returns:
            { "question", "chunks": [(chunk, score), ...] }
        """
        # 1. 查询向量化
        query_embedding = self.embedding.embed([question], is_query=True)[0]

        # 2. 检索
        results = self.vector_store.search(query_embedding, top_k=self.top_k)

        return {
            "question": question,
            "chunks": results,
        }

    @staticmethod
    def format_context(chunks: list[tuple[Chunk, float]]) -> str:
        """将检索结果格式化为 LLM 可消费的上下文文本"""
        parts = []
        for i, (chunk, score) in enumerate(chunks, 1):
            source = chunk.metadata.get("filename", chunk.source)
            parts.append(
                f"[来源{i}] {source} (相关度: {score:.4f})\n{chunk.content}"
            )
        return "\n\n".join(parts)
