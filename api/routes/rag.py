"""RAG 查询接口：检索 + 生成"""

from fastapi import APIRouter
from pydantic import BaseModel

from agentlab.llm import DeepSeekLLM, Message
from agentlab.rag import RAGPipeline

router = APIRouter()

# 延迟初始化
_rag: RAGPipeline | None = None
_llm: DeepSeekLLM | None = None

# RAG 系统提示词（兜底默认；用户可在 /crm 设置页覆盖）
RAG_SYSTEM_PROMPT = (
    "你是一个基于知识库的问答助手。"
    "请根据提供的参考资料回答用户问题。"
    "如果资料中没有相关信息，请明确说明，不要编造答案。"
    "回答要简洁准确，关键信息可引用资料原文。"
)


def get_rag() -> RAGPipeline:
    global _rag
    if _rag is None:
        _rag = RAGPipeline()
    return _rag


def get_llm() -> DeepSeekLLM:
    global _llm
    if _llm is None:
        _llm = DeepSeekLLM()
    return _llm


class RagQueryRequest(BaseModel):
    question: str


class RagSource(BaseModel):
    source: str
    content: str
    score: float


class RagQueryResponse(BaseModel):
    answer: str
    sources: list[RagSource]
    steps: list[dict]


@router.post("/query", response_model=RagQueryResponse)
def query(req: RagQueryRequest):
    """RAG 查询：检索相关文档切块，再由 LLM 生成回答"""
    rag = get_rag()
    llm = get_llm()
    steps: list[dict] = []

    # Step 1: 检索
    result = rag.query(req.question)
    chunks = result["chunks"]

    sources = [
        {
            "source": c.metadata.get("filename", c.source),
            "content": c.content,
            "score": float(score),
        }
        for c, score in chunks
    ]
    steps.append(
        {
            "step": 1,
            "type": "retrieval",
            "content": f"检索到 {len(chunks)} 个相关切块",
            "sources": sources,
        }
    )

    # 组装上下文
    context = RAGPipeline.format_context(chunks)

    # Step 2: LLM 生成
    from agentlab.crm_settings import get_settings

    prompt = get_settings().get("rag_system_prompt") or RAG_SYSTEM_PROMPT
    messages = [
        Message(role="system", content=prompt),
        Message(
            role="user",
            content=f"参考资料：\n\n{context}\n\n用户问题：{req.question}",
        ),
    ]
    response = llm.chat(messages)
    answer = response.content or ""

    if response.reasoning:
        steps.append(
            {
                "step": 2,
                "type": "reasoning",
                "content": response.reasoning,
            }
        )

    steps.append(
        {
            "step": len(steps) + 1,
            "type": "response",
            "content": answer,
        }
    )

    return RagQueryResponse(answer=answer, sources=sources, steps=steps)
