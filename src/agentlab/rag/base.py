"""RAG 基础抽象：数据结构与接口定义"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Document:
    """原始文档"""

    source: str  # 文件路径或来源标识
    content: str  # 纯文本内容
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Chunk:
    """文本切块"""

    chunk_id: str  # 确定性 ID（sha256）
    source: str  # 来源文档
    content: str  # 切块文本
    chunk_index: int  # 在文档中的序号
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseEmbedding(ABC):
    """Embedding 抽象基类"""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化"""
        ...

    @property
    @abstractmethod
    def dimension(self) -> int:
        """向量维度"""
        ...


class BaseVectorStore(ABC):
    """向量存储抽象基类"""

    @abstractmethod
    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        """写入切块及其向量"""
        ...

    @abstractmethod
    def search(
        self, query_embedding: list[float], top_k: int = 4
    ) -> list[tuple[Chunk, float]]:
        """相似度检索，返回 (chunk, score) 列表"""
        ...
