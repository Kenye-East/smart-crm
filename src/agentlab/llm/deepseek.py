"""DeepSeek LLM 实现"""

import json
import os
from typing import Any

from openai import OpenAI

from .base import BaseLLM, Message, ToolCall


class DeepSeekLLM(BaseLLM):
    """DeepSeek API 封装"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "deepseek-v4-flash",
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = model

        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not set")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Message:
        # 转换为 OpenAI 格式
        openai_messages = []
        for msg in messages:
            m: dict[str, Any] = {"role": msg.role}
            if msg.content is not None:
                m["content"] = msg.content
            if msg.tool_calls is not None:
                m["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)},
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id is not None:
                m["tool_call_id"] = msg.tool_call_id
            if msg.name is not None:
                m["name"] = msg.name
            openai_messages.append(m)

        # 构建请求参数
        params: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
        }
        if tools:
            params["tools"] = tools

        # 调用 API
        response = self.client.chat.completions.create(**params)
        choice = response.choices[0]
        msg = choice.message

        # 解析响应
        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                )
                for tc in msg.tool_calls
            ]

        # 提取 reasoning_content（DeepSeek 特有字段）
        # OpenAI SDK 可能不解析此字段，需要从原始数据获取
        reasoning = None
        raw_msg = msg.model_dump() if hasattr(msg, "model_dump") else {}
        reasoning = raw_msg.get("reasoning_content")

        return Message(
            role=msg.role,
            content=msg.content,
            reasoning=reasoning,
            tool_calls=tool_calls,
        )
