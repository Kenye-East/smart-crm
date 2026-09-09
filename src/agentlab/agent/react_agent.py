"""ReAct Agent 实现"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..llm.base import BaseLLM, Message, ToolCall
from ..tools.base import Tool
from .base import BaseAgent


@dataclass
class ExecutionStep:
    """执行步骤"""
    step: int
    type: str  # "reasoning", "thinking", "tool_call", "response"
    content: str | None = None
    tool_name: str | None = None
    arguments: dict[str, Any] | None = None
    result: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ReactAgent(BaseAgent):
    """
    ReAct Agent 实现

    主循环：感知 → 思考 → 行动 → 观察 → 循环
    """

    def __init__(
        self,
        llm: BaseLLM,
        tools: list[Tool],
        system_prompt: str = "你是一个有帮助的助手。",
        max_iterations: int = 10,
    ):
        self.llm = llm
        self.tools = {tool.name: tool for tool in tools}
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations

        # 对话历史
        self.messages: list[Message] = [Message(role="system", content=system_prompt)]
        
        # 执行历史（用于前端展示）
        self.execution_history: list[ExecutionStep] = []
        self._step_counter = 0

    def run(self, user_input: str) -> str:
        """
        执行 Agent 主循环

        Args:
            user_input: 用户输入

        Returns:
            最终响应
        """
        # 清空上一轮的执行历史
        self.execution_history = []
        self._step_counter = 0

        # 添加用户消息
        self.messages.append(Message(role="user", content=user_input))

        # 准备工具定义
        tools_schema = [tool.to_dict() for tool in self.tools.values()] if self.tools else None

        # 主循环
        for iteration in range(self.max_iterations):
            print(f"\n{'='*50}")
            print(f"Iteration {iteration + 1}")
            print(f"{'='*50}")

            # 调用 LLM
            response = self.llm.chat(self.messages, tools=tools_schema)
            print(f"LLM Response: {response}")

            # 情况1：LLM 直接返回文本（无工具调用）
            if not response.tool_calls:
                # 记录推理过程（如果有）
                if response.reasoning:
                    self._step_counter += 1
                    self.execution_history.append(ExecutionStep(
                        step=self._step_counter,
                        type="reasoning",
                        content=response.reasoning,
                    ))
                
                # 记录最终响应
                self._step_counter += 1
                self.execution_history.append(ExecutionStep(
                    step=self._step_counter,
                    type="response",
                    content=response.content or "",
                ))
                
                self.messages.append(response)
                return response.content or ""

            # 情况2：LLM 请求调用工具
            # 记录推理过程（如果有）
            if response.reasoning:
                self._step_counter += 1
                self.execution_history.append(ExecutionStep(
                    step=self._step_counter,
                    type="reasoning",
                    content=response.reasoning,
                ))
            
            # 记录思考步骤（如果有思考内容）
            if response.content:
                self._step_counter += 1
                self.execution_history.append(ExecutionStep(
                    step=self._step_counter,
                    type="thinking",
                    content=response.content,
                ))
            
            self.messages.append(response)

            # 执行每个工具调用
            for tool_call in response.tool_calls:
                print(f"\nCalling tool: {tool_call.name}({tool_call.arguments})")
                result = self._execute_tool(tool_call)
                print(f"Tool result: {result}")

                # 记录工具调用步骤
                self._step_counter += 1
                self.execution_history.append(ExecutionStep(
                    step=self._step_counter,
                    type="tool_call",
                    tool_name=tool_call.name,
                    arguments=tool_call.arguments,
                    result=result,
                ))

                # 添加工具结果到历史
                self.messages.append(
                    Message(
                        role="tool",
                        content=result,
                        tool_call_id=tool_call.id,
                        name=tool_call.name,
                    )
                )

        return "达到最大迭代次数，停止执行。"

    def _execute_tool(self, tool_call: ToolCall) -> str:
        """执行工具调用"""
        if tool_call.name not in self.tools:
            return f"错误：未知工具 '{tool_call.name}'"

        try:
            return self.tools[tool_call.name].run(**tool_call.arguments)
        except Exception as e:
            return f"工具执行错误：{e}"

    def get_execution_history(self) -> list[dict[str, Any]]:
        """获取执行历史（用于 API 返回）"""
        return [
            {
                "step": step.step,
                "type": step.type,
                "content": step.content,
                "tool_name": step.tool_name,
                "arguments": step.arguments,
                "result": step.result,
                "timestamp": step.timestamp,
            }
            for step in self.execution_history
        ]

    def reset(self) -> None:
        """重置对话历史"""
        self.messages = [Message(role="system", content=self.system_prompt)]
        self.execution_history = []
        self._step_counter = 0
