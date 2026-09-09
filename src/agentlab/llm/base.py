"""LLM 基础抽象"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class Message:
    """消息格式"""
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | None = None
    reasoning: str | None = None
    tool_calls: list["ToolCall"] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolCall:
    """工具调用请求"""
    id: str
    name: str
    arguments: dict[str, Any]


class BaseLLM(ABC):
    """LLM 抽象基类"""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Message:
        """
        发送对话请求

        Args:
            messages: 对话历史
            tools: 可用工具定义（JSON Schema 格式）

        Returns:
            LLM 响应消息
        """
        pass
