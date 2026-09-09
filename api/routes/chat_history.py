"""对话记录查询接口（/api/chat-history）

读取 wechat_rpa 写入的 data/chat_history.db，供 /crm 后台展示：
- GET /api/chat-history/conversations          会话列表（含统计所需摘要）
- GET /api/chat-history/conversations/{contact} 单会话时间线
- GET /api/chat-history/stats                  聚合统计卡片
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentlab.chat_store import ChatStore

router = APIRouter()

_store = ChatStore()  # 模块级单例，读多，WAL + 函数级连接保证线程安全


class ConversationSummary(BaseModel):
    contact: str
    avatar_color: str
    latest_message: str
    message_count: int
    updated_at: int


class MessageItem(BaseModel):
    id: int
    role: str
    content: str
    source_chunks: list[dict] | None
    status: str
    qa_reason: str | None
    duration_ms: int | None
    created_at: int


class StatsResponse(BaseModel):
    total_conversations: int
    total_messages: int
    ai_replies: int
    success_rate: float
    avg_duration_ms: float
    today_messages: int
    week_messages: int


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations():
    return _store.list_conversations()


@router.get("/conversations/{contact}", response_model=list[MessageItem])
def get_conversation(contact: str):
    msgs = _store.get_conversation(contact)
    if not msgs:
        raise HTTPException(status_code=404, detail="会话不存在")
    return msgs


@router.get("/stats", response_model=StatsResponse)
def stats():
    return _store.stats()