"""Embedding 实现：基于 sentence-transformers 的 bge-base-zh-v1.5"""

import os

from sentence_transformers import SentenceTransformer

from .base import BaseEmbedding

# BGE 中文检索模型对 query 的推荐前缀（提升检索效果）
BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

# 默认模型：优先使用项目内置的本地模型（离线可用）
DEFAULT_MODEL_NAME = "BAAI/bge-base-zh-v1.5"
LOCAL_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "models",
    "bge-base-zh-v1.5",
)


def _resolve_model_name() -> str:
    """解析实际使用的模型路径/名称

    优先级：环境变量 RAG_EMBEDDING_MODEL > 项目本地模型目录 > HuggingFace 模型名
    """
    env_model = os.getenv("RAG_EMBEDDING_MODEL")
    if env_model:
        return env_model
    if os.path.isdir(LOCAL_MODEL_DIR):
        return LOCAL_MODEL_DIR
    return DEFAULT_MODEL_NAME


class BGESentenceEmbedding(BaseEmbedding):
    """使用 sentence-transformers 加载 BGE 中文 embedding 模型"""

    def __init__(
        self,
        model_name: str | None = None,
        query_instruction: str | None = None,
        device: str | None = None,
    ):
        self.model_name = model_name or _resolve_model_name()
        self.query_instruction = (
            query_instruction
            if query_instruction is not None
            else BGE_QUERY_INSTRUCTION
        )
        self.device = device or os.getenv("RAG_DEVICE", "cpu")

        # 延迟加载模型（首次 embed 时才下载/加载）
        self._model: SentenceTransformer | None = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(
                self.model_name, device=self.device
            )
        return self._model

    @property
    def dimension(self) -> int:
        model = self._get_model()
        # 兼容新旧版本 API
        if hasattr(model, "get_embedding_dimension"):
            return model.get_embedding_dimension()
        return model.get_sentence_embedding_dimension()

    def embed(self, texts: list[str], is_query: bool = False) -> list[list[float]]:
        """
        批量向量化

        Args:
            texts: 文本列表
            is_query: 是否为查询文本（True 时添加检索前缀）

        Returns:
            向量列表
        """
        model = self._get_model()
        if is_query and self.query_instruction:
            texts = [self.query_instruction + t for t in texts]

        embeddings = model.encode(
            texts,
            normalize_embeddings=True,  # L2 归一化，便于余弦相似度
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings.tolist()
