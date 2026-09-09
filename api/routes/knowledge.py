"""知识库管理接口（/api/knowledge）

- POST /upload  上传文件到 knowledge/ 并在后台重新全量索引
- GET  /list    列出 knowledge/ 下的文件
- GET  /status  查询最近一次重建状态（running/last_status/last_error）
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from fastapi import APIRouter, UploadFile

router = APIRouter()

# 仓库根的 knowledge 目录（与 scripts/index_knowledge.py 同根）
KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "knowledge"

# 重建状态（跨请求共享，模块级）
_state = {
    "running": False,
    "last_status": None,
    "last_error": None,
    "last_at": None,
    "lock": threading.Lock(),
}


def _rebuild() -> None:
    """后台执行全量重建向量库。"""
    with _state["lock"]:
        if _state["running"]:
            return
        _state["running"] = True
        _state["last_error"] = None
        _state["last_at"] = time.time()

    try:
        from agentlab.rag import RAGPipeline  # 延迟导入，避免启动耦合

        pipeline = RAGPipeline()  # 新实例，不用 rag.py 单例（避免旧句柄）
        _state["last_status"] = pipeline.index(str(KNOWLEDGE_DIR))
    except Exception as e:  # 重建失败记录错误，不抛到线程外
        _state["last_error"] = str(e)
    finally:
        _state["running"] = False


@router.post("/upload")
def upload(file: UploadFile):
    # 文件名安全化：仅取 basename，防路径穿越
    name = Path(file.filename or "").name or "unnamed"
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    (KNOWLEDGE_DIR / name).write_bytes(file.file.read())

    _rebuild()  # 后台线程重建（daemon，不阻塞响应）
    return {"ok": True, "filename": name, "rebuild": "started"}


@router.get("/list")
def list_files():
    if not KNOWLEDGE_DIR.exists():
        return []
    out = []
    for p in sorted(KNOWLEDGE_DIR.iterdir()):
        if p.is_file() and not p.name.startswith("."):
            out.append(
                {
                    "name": p.name,
                    "size": p.stat().st_size,
                    "mtime": int(p.stat().st_mtime),
                }
            )
    return out


@router.get("/status")
def rebuild_status():
    return {
        "running": _state["running"],
        "last_status": _state["last_status"],
        "last_error": _state["last_error"],
        "last_at": _state["last_at"],
    }