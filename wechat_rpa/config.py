"""微信 RPA 自动回复 - 配置

坐标框默认值是占位，请用 calibrate_gui.py 图形化校准。
校准结果写入 calibrated.json，会被自动优先加载。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# 校准结果文件（与 config.py 同目录）
CALIB_FILE = Path(__file__).with_name("calibrated.json")


@dataclass
class Region:
    """屏幕矩形区域"""

    left: int
    top: int
    width: int
    height: int


@dataclass
class Config:
    # ---- 屏幕区域校准（必须调整，单位：像素） ----
    # 微信主窗口在屏幕上的位置。把微信窗口拖到固定位置后填入。
    # 会话列表区域：左侧一栏，显示各联系人/群。用于检测"谁在给你发消息"。
    chat_list_region: Region = field(default_factory=lambda: Region(left=0, top=80, width=240, height=700))
    # 聊天内容区域：右侧消息区。用于读取对方发来的消息文本。
    chat_content_region: Region = field(default_factory=lambda: Region(left=240, top=80, width=800, height=600))
    # 输入框位置：聊天区下方，用于定位光标后输入。
    input_box_pos: tuple[int, int] = (400, 780)

    # ---- 目标联系人 ----
    # 只回复命中的人发来的消息。采用"包含匹配"：
    #   会话列表里出现 任意一个关键词 的子串 就算命中（不要求完全一致）
    # 例：["李", "张三"] → "李总"、"王李"、"张三丰" 都会被命中
    target_contacts: list[str] = field(default_factory=lambda: ["李", "K"])

    # ---- 轮询参数 ----
    poll_interval: float = 15.0  # 每次检测间隔（秒）
    diff_threshold: int = 30  # 文本差异字符数阈值，超过则视为新消息
    max_history_turns: int = 4  # 回复时携带最近几轮对话上下文

    # ---- RAG 调用方式 ----
    # "local" = 直接复用本地 RAGPipeline（推荐，无需起服务）
    # "http"  = 调用 FastAPI 的 /api/rag/query
    rag_mode: str = "local"
    rag_http_url: str = "http://127.0.0.1:8000/api/rag/query"

    # ---- 行为开关 ----
    auto_send: bool = True  # True=自动发送回复；False=只打印，不点发送（调试用）

    # ---- 拟人输入（模拟打字节奏，分段粘贴上屏）----
    typing_imitation: bool = True       # True=分段逐段粘贴出"打字感"；False=整段一次粘
    typing_chars_per_segment: int = 3   # 每段粘贴的字符数；设为 1 即严格逐字
    typing_delay: tuple = (0.35, 0.9)   # 每段之间随机停顿（秒），放慢更显自然
    send_delay: tuple = (1.0, 2.2)      # 全部上屏后、按回车发送前的停顿（秒）

    # ---- 微信自动回复系统提示词（默认；可从 /crm 后台覆盖）----
    wechat_system_prompt: str = field(
        default=(
            "你在帮我回微信消息，要让对方觉得就是我在跟你聊，自然、不像是机器人。"
            "语气要求：口语化、像朋友随口说话；用词随意自然，可以带一点生活感；"
            "多一两句话就有来有回，一般两三句内说完，别写长篇、别列点、别用书面语。"
            "内容以我给你的参考资料为准，知道什么就自然告诉对方，"
            "不要提到资料、知识库、机器人、客服、AI 这些词。"
            "资料里没有明确答案的，就坦诚说『这个我还真不确定，等我确认下再回你』，别硬编。"
        )
    )

    # ---- 发送前质检（可供 /crm 后台覆盖）----
    quality_enabled: bool = True  # True=每次发送前先过质检；False=跳过
    max_qa_retry: int = 2         # 质检拦截后最多重新生成几次
    quality_system_prompt: str = field(
        default=(
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
    )

    # ---------- 校准文件加载 ----------
    @classmethod
    def load(cls) -> "Config":
        """创建 Config；若存在 calibrated.json 则用其中坐标覆盖区域字段"""
        cfg = cls()
        if CALIB_FILE.exists():
            data = json.loads(CALIB_FILE.read_text(encoding="utf-8"))
            if "chat_list_region" in data:
                cfg.chat_list_region = Region(**data["chat_list_region"])
            if "chat_content_region" in data:
                cfg.chat_content_region = Region(**data["chat_content_region"])
            if "input_box_pos" in data:
                cfg.input_box_pos = tuple(data["input_box_pos"])

        # 后台(/crm)保存的业务配置覆盖业务参数（下次启动生效）
        try:
            from agentlab.crm_settings import get_settings

            s = get_settings()
            if s.get("target_contacts"):
                cfg.target_contacts = list(s["target_contacts"])
            if s.get("poll_interval"):
                cfg.poll_interval = float(s["poll_interval"])
            if s.get("wechat_system_prompt") is not None:
                cfg.wechat_system_prompt = s["wechat_system_prompt"]
            if s.get("quality_system_prompt") is not None and s["quality_system_prompt"]:
                cfg.quality_system_prompt = s["quality_system_prompt"]
            if s.get("quality_enabled") is not None:
                cfg.quality_enabled = bool(s["quality_enabled"])
        except Exception:
            pass  # 配置读取失败不阻断启动，沿用代码默认值
        return cfg