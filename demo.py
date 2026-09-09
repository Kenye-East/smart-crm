"""
Smart CRM Demo - 第一个 Agent

运行方式：
1. 复制 .env.example 为 .env，填入你的 DeepSeek API Key
2. python demo.py
"""

import os
from dotenv import load_dotenv

from agentlab.llm import DeepSeekLLM
from agentlab.tools import CalculatorTool, WeatherTool
from agentlab.agent import ReactAgent


def main():
    # 加载环境变量
    load_dotenv()

    # 初始化 LLM
    llm = DeepSeekLLM()

    # 初始化工具
    tools = [CalculatorTool, WeatherTool]

    # 创建 Agent
    agent = ReactAgent(
        llm=llm,
        tools=tools,
        system_prompt="你是一个有帮助的助手。可以计算数学表达式和查询天气。",
    )

    # 测试对话
    print("=" * 60)
    print("Smart CRM Demo - 输入 'quit' 退出")
    print("=" * 60)

    while True:
        user_input = input("\n你：").strip()
        if user_input.lower() in ("quit", "exit", "q"):
            print("再见！")
            break

        if not user_input:
            continue

        response = agent.run(user_input)
        print(f"\nAgent：{response}")


if __name__ == "__main__":
    main()
