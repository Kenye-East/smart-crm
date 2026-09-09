"""
Smart CRM 一键启动 - 启动 FastAPI 后端 + Next.js 前端，并自动打开页面

用法:
    python start_agent.py            # 默认 react Agent
    python start_agent.py react      # 指定 react
"""

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# 项目根目录
PROJECT_ROOT = Path(__file__).parent
BACKEND_URL = "http://localhost:8000"
FRONTEND_URL = "http://localhost:3000"
MAX_WAIT_SECONDS = 60  # 等待服务就绪的最长时间


def wait_for_ready(url: str, timeout: int = MAX_WAIT_SECONDS) -> bool:
    """轮询探测 HTTP 服务是否就绪"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def start_services(agent_type: str):
    """启动 FastAPI 后端 + Next.js 前端"""

    # 设置环境变量，指定 Agent 类型
    os.environ["AGENT_TYPE"] = agent_type

    print(f"正在启动 {agent_type} Agent 服务...")
    print("-" * 50)

    # 第一步先启动 FastAPI 后端
    print("启动 FastAPI 后端 (端口 8000)...")
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--port", "8000"],
        cwd=PROJECT_ROOT,
    )

    # 等后端就绪后再启动前端，避免前端抢跑连不上后端
    print("等待后端就绪...")
    if not wait_for_ready(BACKEND_URL + "/health"):
        print("警告: 后端未在预期时间内就绪，仍尝试启动前端")
    else:
        print("  后端已就绪 ✓")

    # 第二步启动 Next.js 前端
    print("启动 Next.js 前端 (端口 3000)...")
    frontend = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=PROJECT_ROOT / "web",
        shell=True,  # Windows 需要 shell=True
    )

    try:
        # 等待前端就绪
        print("等待前端就绪...")
        if not wait_for_ready(FRONTEND_URL):
            print("警告: 前端未在预期时间内就绪")
        else:
            print("  前端已就绪 ✓")
            # 自动打开浏览器（默认进入 /crm 对话后台）
            webbrowser.open(FRONTEND_URL + "/crm")

        print("-" * 50)
        print(f"  后端: {BACKEND_URL}")
        print(f"  前端: {FRONTEND_URL}")
        print("  按 Ctrl+C 停止所有服务")
        print("-" * 50)

        # 等待任一进程退出
        while True:
            if backend.poll() is not None:
                print("后端服务已退出")
                break
            if frontend.poll() is not None:
                print("前端服务已退出")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务...")
    finally:
        backend.terminate()
        frontend.terminate()
        backend.wait()
        frontend.wait()
        print("所有服务已停止")


def main():
    parser = argparse.ArgumentParser(description="Agent 快速启动脚本")
    parser.add_argument(
        "agent_type",
        nargs="?",
        default="react",
        choices=["react", "plan-and-execute"],
        help="要启动的 Agent 类型（默认 react）",
    )
    args = parser.parse_args()
    start_services(args.agent_type)


if __name__ == "__main__":
    main()
