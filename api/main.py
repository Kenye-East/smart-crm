"""FastAPI 后端入口"""

import os
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import chat, chat_history, crm_settings, knowledge, rag

# 加载环境变量
load_dotenv()

app = FastAPI(title="Smart CRM API")

# CORS 配置（允许 Next.js 访问）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(chat.router, prefix="/api")
app.include_router(rag.router, prefix="/api/rag")
app.include_router(chat_history.router, prefix="/api/chat-history")
app.include_router(crm_settings.router, prefix="/api/crm-settings")
app.include_router(knowledge.router, prefix="/api/knowledge")


@app.get("/health")
def health():
    return {"status": "ok"}
