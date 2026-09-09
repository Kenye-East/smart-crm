"""工具基础抽象"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema
    func: Callable[..., str]

    def to_dict(self) -> dict[str, Any]:
        """转换为 OpenAI tool 格式"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def run(self, **kwargs: Any) -> str:
        """执行工具"""
        return self.func(**kwargs)


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
) -> Callable[[Callable[..., str]], Tool]:
    """装饰器：将函数转换为 Tool"""
    def decorator(func: Callable[..., str]) -> Tool:
        return Tool(name=name, description=description, parameters=parameters, func=func)
    return decorator
