"""Agent 抽象基类"""

from abc import ABC, abstractmethod

from ..llm.base import BaseLLM
from ..tools.base import Tool


class BaseAgent(ABC):
    """
    Agent 抽象基类

    所有 Agent 实现必须继承此类并实现 run 方法。
    """

    @abstractmethod
    def run(self, user_input: str) -> str:
        """
        执行 Agent

        Args:
            user_input: 用户输入

        Returns:
            Agent 响应
        """
        pass

    @abstractmethod
    def reset(self) -> None:
        """重置 Agent 状态"""
        pass
