"""聊天接口"""

import os

from fastapi import APIRouter
from pydantic import BaseModel

from agentlab.llm import DeepSeekLLM
from agentlab.tools import CalculatorTool, WeatherTool
from agentlab.agent import ReactAgent

router = APIRouter()

# 延迟初始化 Agent
_agent = None

# 工具列表
TOOLS = [CalculatorTool, WeatherTool]

# Agent 类型映射
AGENT_TYPES = {
    "react": ReactAgent,
    # "plan-and-execute": PlanAndExecuteAgent,  # 待实现
}


def get_agent():
    global _agent
    if _agent is None:
        agent_type = os.environ.get("AGENT_TYPE", "react")
        agent_class = AGENT_TYPES.get(agent_type)
        
        if agent_class is None:
            raise ValueError(f"未知的 Agent 类型: {agent_type}，支持: {list(AGENT_TYPES.keys())}")
        
        llm = DeepSeekLLM()
        _agent = agent_class(
            llm=llm,
            tools=TOOLS,
            system_prompt="你是一个有帮助的助手。可以计算数学表达式和查询天气。",
        )
    return _agent


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str
    steps: list[dict]


@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """聊天接口"""
    agent = get_agent()
    response = agent.run(req.message)
    steps = agent.get_execution_history()
    return ChatResponse(response=response, steps=steps)


@router.post("/reset")
def reset():
    """重置对话"""
    agent = get_agent()
    agent.reset()
    return {"status": "ok"}
