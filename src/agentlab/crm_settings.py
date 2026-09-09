"""后台可配置项（/crm 侧修改，wechat_rpa 下次启动读取）。

与 data/chat_history.db 同目录，存 data/crm_settings.json。
- 由 FastAPI（/crm）写入，wechat_rpa 启动时读取；
- 原子写（先写 .tmp 再 os.replace），模块级锁保护并发读写；
- 两个 system prompt 默认文案作为"单一事实来源"落在本文件，
  空串在读取端视为"未配置"，由使用方回退默认文案。
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

SETTINGS_PATH = Path(__file__).resolve().parents[2] / "data" / "crm_settings.json"

# 微信自动回复系统提示词（默认 = responder.py 原内嵌文案）
_DEFAULT_WECHAT_PROMPT = (
    "你在帮我回微信消息，要让对方觉得就是我在跟你聊，自然、不像是机器人。"
    "语气要求：口语化、像朋友随口说话；用词随意自然，可以带一点生活感；"
    "多一两句话就有来有回，一般两三句内说完，别写长篇、别列点、别用书面语。"
    "内容以我给你的参考资料为准，知道什么就自然告诉对方，"
    "不要提到资料、知识库、机器人、客服、AI 这些词。"
    "资料里没有明确答案的，就坦诚说『这个我还真不确定，等我确认下再回你』，别硬编。"
)

# RAG 接口系统提示词（默认 = api/routes/rag.py 原 RAG_SYSTEM_PROMPT）
_DEFAULT_RAG_PROMPT = (
    "你是一个基于知识库的问答助手。"
    "请根据提供的参考资料回答用户问题。"
    "如果资料中没有相关信息，请明确说明，不要编造答案。"
    "回答要简洁准确，关键信息可引用资料原文。"
)

# 质检 Agent 系统提示词（默认）：发送前逐条审查回复是否高危
_DEFAULT_QUALITY_PROMPT = (
    "你是微信人工回复的质检员，负责在消息发送前审查回复内容。"
    "对方刚发来一条消息，AI 拟好了一条待发送的回复，你要判断这条回复是否存在高危风险。"
    "认定为高危（需拦截）的情形包括但不限于："
    "① 违法违规：涉及赌博、毒品、诈骗、色情、政治敏感、传销洗脑、诱导参与违法活动；"
    "② 泄露隐私/机密：透露他人隐私、个人身份证/银行卡等敏感信息、公司机密、内部资料；"
    "③ 人身风险：辱骂、威胁、恐吓、贬低对方或第三方；"
    "④ 严重误导：承诺无法兑现的收益/返利、诱导转账汇款、虚假保证。"
    "只要命中上述任一情形即判为拦截；反之为通过。"
    "请严格只输出一行 JSON，不要输出其它文字，格式："
    '{"pass": true 或 false, "reason": "一句话说明拦截原因（通过则填 null）"}'
)

_lock = threading.Lock()


def _defaults() -> dict:
    return {
        "target_contacts": ["李", "K"],
        "poll_interval": 15.0,
        "quality_enabled": True,
        "wechat_system_prompt": _DEFAULT_WECHAT_PROMPT,
        "rag_system_prompt": _DEFAULT_RAG_PROMPT,
        "quality_system_prompt": _DEFAULT_QUALITY_PROMPT,
    }


def get_settings() -> dict:
    """读取配置，缺项用默认值兜底。文件不存在返回默认全量。"""
    with _lock:
        merged = _defaults()
        if SETTINGS_PATH.exists():
            try:
                data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    merged.update({k: v for k, v in data.items() if v is not None})
            except (json.JSONDecodeError, OSError):
                # 损坏/读不了就返回默认值，不抛错
                pass
        return merged


def update_settings(patch: dict) -> dict:
    """合并 → 校验 → 原子写 → 返回全量有效配置。"""
    with _lock:
        merged = _defaults()
        if SETTINGS_PATH.exists():
            try:
                existing = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    merged.update({k: v for k, v in existing.items() if v is not None})
            except (json.JSONDecodeError, OSError):
                merged = _defaults()

        # 合并补丁
        for key, val in patch.items():
            if val is not None:
                merged[key] = val

        # 校验
        cur = merged["target_contacts"]
        if not isinstance(cur, list):
            merged["target_contacts"] = _defaults()["target_contacts"]
        else:
            cleaned = [str(c).strip() for c in cur if str(c).strip()]
            merged["target_contacts"] = list(dict.fromkeys(cleaned))  # 去重保序
            if not merged["target_contacts"]:
                merged["target_contacts"] = _defaults()["target_contacts"]

        try:
            interval = float(merged["poll_interval"])
            if interval <= 0:
                raise ValueError
            merged["poll_interval"] = interval
        except (TypeError, ValueError):
            merged["poll_interval"] = _defaults()["poll_interval"]

        merged["quality_enabled"] = bool(merged["quality_enabled"])

        # prompt 允许空串
        merged["wechat_system_prompt"] = str(merged["wechat_system_prompt"])
        merged["rag_system_prompt"] = str(merged["rag_system_prompt"])
        merged["quality_system_prompt"] = str(merged["quality_system_prompt"])

        # 原子写
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS_PATH.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp, SETTINGS_PATH)
        return merged