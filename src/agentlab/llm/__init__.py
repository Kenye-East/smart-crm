"""LLM 抽象层"""

from .base import BaseLLM, Message, ToolCall
from .deepseek import DeepSeekLLM

__all__ = ["BaseLLM", "Message", "ToolCall", "DeepSeekLLM"]
