"""执行层：桥接 RAG 并自动回复

包含：
- 从消息文本调用 RAG 获取回答（local 直接调用 / http 调接口两种模式）
- 通过 pyautogui 模拟点击输入框、键入并发送回复
"""
from __future__ import annotations

import random
import re
import time

import pyautogui
import pyperclip

from .config import Config


def _split_segments(text: str, chars_per_segment: int) -> list[str]:
    """把回答拆成小段，供分段粘贴模拟打字。

    优先在中文/英文标点后断开，再按字符数合并成每段约 chars_per_segment 个字符。
    chars_per_segment=1 即严格一个字一段。
    """
    n = max(int(chars_per_segment), 1)
    parts = [p for p in re.split(r"([。！？!?；;，,、…\n])", text) if p]
    segs: list[str] = []
    buf = ""
    for p in parts:
        buf += p
        if len(buf) >= n:
            segs.append(buf)
            buf = ""
    if buf:
        segs.append(buf)
    return segs or [text]


class RagResponder:
    """根据用户问题获取 RAG 回答"""

    def __init__(self, config: Config):
        self.config = config
        self._pipeline = None

    def _get_pipeline(self):
        """local 模式下的本地 RAG 管线（懒加载）"""
        if self._pipeline is None:
            from agentlab.rag import RAGPipeline

            self._pipeline = RAGPipeline()
        return self._pipeline

    def answer(self, question: str, reject_reason: str | None = None) -> str:
        """获取回答。reject_reason 非空时，提示模型上次回复被质检拦截、换一种更稳妥的说法。"""
        q = question.strip()
        if not q:
            return ""

        cfg = self.config
        if cfg.rag_mode == "http":
            return self._answer_http(q)
        return self._answer_local(q, reject_reason)

    def _answer_local(self, question: str, reject_reason: str | None = None) -> str:
        """复用本地 RAGPipeline"""
        try:
            result = self._get_pipeline().query(question)
            chunks = result["chunks"]
            if not chunks:
                return "这个我还真不太确定，等我查一下再回你哈"
            # 直接用查询结果拼 context，再由 LLM 生成
            from agentlab.llm import DeepSeekLLM, Message
            from agentlab.rag import RAGPipeline as RP

            context = RP.format_context(chunks)
            user = f"参考资料：\n\n{context}\n\n对方刚问：{question}"
            if reject_reason:
                user += (
                    f"\n\n注意：上一版回复因质检拦截不能发送（原因：{reject_reason}）。"
                    "请重新组织回答，换一种更稳妥、不同的话术，避开上述风险点，但不要生硬地提抱歉。"
                )
            llm = DeepSeekLLM()
            messages = [
                Message(role="system", content=self.config.wechat_system_prompt),
                Message(role="user", content=user),
            ]
            resp = llm.chat(messages)
            return resp.content or ""
        except Exception as e:  # 网络/模型异常时兜底，不把异常抛到主循环
            return "我先不说了，回头再回你哈"

    def _answer_http(self, question: str) -> str:
        """调用 FastAPI 的 /api/rag/query"""
        import json
        import urllib.request

        data = json.dumps({"question": question}).encode("utf-8")
        req = urllib.request.Request(
            self.config.rag_http_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body.get("answer", "")


class WeChatSender:
    """通过 pyautogui 在微信输入框中发送文本"""

    def __init__(self, config: Config):
        self.config = config

    def focus_input(self):
        """点击输入框获取焦点"""
        x, y = self.config.input_box_pos
        pyautogui.click(x, y)

    def send(self, text: str):
        if not text:
            return
        self.focus_input()
        time.sleep(random.uniform(0.4, 0.8))  # 点输入框后略顿，模拟落座

        cfg = self.config
        if cfg.typing_imitation:
            # 分段粘贴模拟打字：逐段 ctrl+v，段间随机停顿
            for seg in _split_segments(text, cfg.typing_chars_per_segment):
                pyperclip.copy(seg)
                pyautogui.hotkey("ctrl", "v")
                time.sleep(random.uniform(*cfg.typing_delay))
        else:
            # 整段一次粘贴
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            time.sleep(random.uniform(0.6, 1.2))

        # 全部上屏后再停顿一下才回车，模拟"写完停一下再发送"
        time.sleep(random.uniform(*cfg.send_delay))
        pyautogui.press("enter")


class RiskChecker:
    """发送前质检 Agent：判断回复是否高危。拦截则返回 (True, 原因)，通过返回 (False, None)。"""

    def __init__(self, config: Config):
        self.config = config

    def check(self, question: str, reply: str) -> tuple[bool, str | None]:
        if not reply or not reply.strip():
            return False, None  # 空回复不拦截（上游已兜底不发）

        import json as _json

        from agentlab.llm import DeepSeekLLM, Message

        llm = DeepSeekLLM()
        messages = [
            Message(role="system", content=self.config.quality_system_prompt),
            Message(
                role="user",
                content=f"对方消息：\n{question}\n\n待发送回复：\n{reply}",
            ),
        ]
        try:
            out = (llm.chat(messages).content or "").strip()
            # 取第一行，按 JSON 解析
            first_line = next((ln for ln in out.splitlines() if ln.strip()), "")
            tag = first_line.strip().strip("`")
            data = _json.loads(tag) if tag.startswith("{") else _json.loads(_extract_json(out))
            blocked = bool(data.get("pass")) is False
            reason = data.get("reason")
            if blocked and not reason:
                reason = "质检未通过"
            return blocked, (reason if blocked else None)
        except Exception as e:  # 质检调用/解析失败 → 放行，避免误拦截正常回复
            print(f"[质检] 调用异常，本轮放行: {e}")
            return False, None


def _extract_json(text: str) -> str:
    """粗提取第一个 JSON 对象子串，供解析兜底。"""
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return "{}"