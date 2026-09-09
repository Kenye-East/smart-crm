"""微信 RPA 自动回复 - 主入口（会话列表驱动）

运行姿态（重要）：
    微信停留在"会话列表页"（主界面），程序每轮：
    1. OCR 会话列表 → 按行聚合，找出命中目标（如 李/K）的会话行；
    2. 某目标行的"文字指纹"与上一轮不同（= 对方发来新消息/列表变化）
       → 自动点击该行进入对话；
    3. 读取聊天内容区最底部"对方(左侧)"消息 → RAG 回答；
    4. 发送后刷新基准，停留在该对话；
       —— 若其他目标又来新消息，列表变化会被捕获并自动切过去。

只回复会话名（列表最左侧块）命中 target 的行，避免把
"预览文字里恰好提到李/K"的其它会话误判为目标。

用法：
    python -m wechat_rpa.main
"""
from __future__ import annotations

import random
import re
import time

import pyautogui
from dotenv import load_dotenv

from .config import Config
from .responder import RagResponder, RiskChecker, WeChatSender
from agentlab.chat_store import ChatStore
from .vision import (
    capture_region,
    group_into_rows,
    ocr_blocks,
    refine_name_from_strip,
)

# 形如 "09:45" 的时间块 / 纯数字未读块，不比对、也不进指纹
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
BEAT_INTERVAL = 60.0  # 无变化时每隔多久打一次心跳，让用户确认在跑


def _fingerprint(text: str) -> str:
    """行指纹：去掉时间/纯数字后剩余文本，用于判断该行是否变化"""
    toks = [t for t in text.split() if not _TIME_RE.match(t) and not t.isdigit()]
    return " ".join(toks)


def _screen_rows(cfg: Config) -> list[dict]:
    """OCR 会话列表区域并聚合成行（坐标已是屏幕绝对坐标）"""
    reg = cfg.chat_list_region
    image = capture_region(reg)
    blocks = ocr_blocks(image)
    rows = group_into_rows(blocks)
    # 二次精读：名字未命中目标的行，裁名字条 4 倍放大重读，
    # 纠正首遍整图 OCR 漏掉的名字（如单个字母 K）
    for r in rows:
        if not any(t.lower() in r["name"].lower() for t in cfg.target_contacts):
            fixed = refine_name_from_strip(image, r)
            if fixed:
                r["name"] = fixed
    for r in rows:
        r["xc"] = reg.left + r["xc"]
        r["yc"] = reg.top + r["yc"]
    return rows


def _match_target_rows(rows: list[dict], cfg: Config) -> list[dict]:
    """只按会话名（最左侧块）做包含匹配，返回命中目标的行"""
    return [
        r for r in rows
        if any(t.lower() in r["name"].lower() for t in cfg.target_contacts)
    ]


def _latest_incoming_text(cfg: Config) -> str:
    """读聊天内容区最底部、位于中线左侧(=对方发的)文字。

    返回去掉时间块后按从上到下拼接的文本；读不到对方消息
    (最底部是自己在右侧/空/纯表情)时返回 ""。
    """
    reg = cfg.chat_content_region
    blocks = ocr_blocks(capture_region(reg))
    if not blocks:
        return ""
    mid = reg.width / 2
    left_blocks = [
        b for b in blocks
        if b["xc"] < mid and not _TIME_RE.match(b["text"].strip())
    ]
    if not left_blocks:
        return ""
    anchor = max(left_blocks, key=lambda b: b["y1"])  # 最底部对方消息块
    # 向上合并同一气泡/紧邻消息：y 距锚底不超过 90px 的左侧文字块
    parts = [
        b for b in left_blocks
        if b["y1"] <= anchor["y1"] + 1 and anchor["y1"] - b["y0"] <= 90
    ]
    parts.sort(key=lambda b: b["y0"])
    return " ".join(b["text"] for b in parts).strip()


def _qa_generate(responder, checker, cfg, question):
    """生成 → 质检 → 拦截则重发的循环。

    返回 (replies, final_answer, will_send)：
      replies      每条 {status, content, qa_reason}，按序，含被拦截的
      final_answer 最终要发送的文本（质量通过或已达重试上限后的最后一条）
      will_send    True=可以发送；False=重试耗尽仍高危，本次不发送
    """
    answer = responder.answer(question)
    replies: list[dict] = []
    for attempt in range(cfg.max_qa_retry + 1):
        if not cfg.quality_enabled:
            break
        blocked, reason = checker.check(question, answer)
        if not blocked:
            return replies, answer, True
        replies.append({"status": "blocked", "content": answer, "qa_reason": reason})
        print(f"[质检] 拦截第 {len(replies)} 次回复，理由：{reason}")
        if attempt >= cfg.max_qa_retry:
            # 已达到最大重试次数仍高危 → 不再发送
            return replies, answer, False
        answer = responder.answer(question, reject_reason=reason)
    # 未启用质检，或循环自然通过
    return replies, answer, True


def _handle_contact(cfg: Config, responder, checker, sender, row: dict, store: ChatStore):
    """点击进入该会话 → 读最新消息 → 回答并质检 → 发送。回复后停留在该对话。"""
    name = row["name"]
    x, y = int(row["xc"]), int(row["yc"])
    print(f"\n[进入] 命中目标会话 '{name}'，点击 ({x}, {y})")
    pyautogui.click(x, y)
    time.sleep(1.2)  # 等对话窗口切换并渲染完成

    question = _latest_incoming_text(cfg)
    if not question:
        print(f"[等待] 已进入 '{name}'，但未读到对方(左侧)文字，本轮不回复")
        return
    print(f"[问题] {question}")

    t0 = time.time()
    replies, answer, will_send = _qa_generate(responder, checker, cfg, question)
    print(f"[回答] {answer}")

    success = False
    if cfg.auto_send and answer and will_send:
        # 读完后停顿一下再动手输入，模拟"想一下怎么回"
        time.sleep(random.uniform(0.8, 1.8))
        sender.send(answer)
        time.sleep(0.5)
        success = True
        print(f"[发送] 已自动回复，停留在 '{name}' 对话")
    elif not will_send:
        print(f"[拦截] 重试后回复仍高危，本次不发送（共拦截 {len(replies)} 条）")

    duration_ms = int((time.time() - t0) * 1000)
    if replies:
        # 有被拦截的 → 用带质检的记录方法，把拦截与最终回复都入库
        final_status = "sent" if success else "blocked"
        replies.append(
            {"status": final_status, "content": answer, "qa_reason": None}
        )
        store.insert_qc_turn(contact=name, question=question, replies=replies, duration_ms=duration_ms)
    else:
        # 未发生拦截 → 走原路径
        store.insert_record(
            contact=name,
            question=question,
            answer=answer,
            status="sent" if success else "skipped",
            duration_ms=duration_ms,
        )


def main():
    load_dotenv()

    # 尚未校准则自动弹出图形校准工具；用户取消则直接退出，避免循环重弹
    from .calibrate_gui import has_calibration, run_calibration_gui

    if not has_calibration():
        print("=" * 40)
        print("尚未进行屏幕校准，正在打开校准窗口...")
        print("请先在引导窗里把微信调到最前、选好目标会话。")
        print("=" * 40)
        ok = run_calibration_gui()
        if not ok:
            print("\n校准未完成，自动回复无法启动，程序退出。")
            print("请重新运行启动脚本完成校准。")
            return

    cfg = Config.load()
    responder = RagResponder(cfg)
    checker = RiskChecker(cfg)
    sender = WeChatSender(cfg)
    store = ChatStore()  # 对话记录存储（首次会建库并写入示例数据）

    print("=" * 40)
    print("微信 RPA 自动回复（会话列表驱动）")
    print(f"目标联系人: {cfg.target_contacts}")
    print(f"匹配规则: 会话名包含任意关键词即命中")
    print(f"会话列表区域: {cfg.chat_list_region}")
    print(f"聊天内容区域: {cfg.chat_content_region}")
    print(f"输入框位置: {cfg.input_box_pos}")
    print(f"轮询间隔: {cfg.poll_interval}s | RAG 模式: {cfg.rag_mode}")
    print(f"auto_send: {cfg.auto_send} | 质检: {'开' if cfg.quality_enabled else '关'} (拦截重试 {cfg.max_qa_retry} 次)")
    print("请把微信停在【会话列表页】。按 Ctrl+C 停止")
    print("=" * 40)

    snapshot: dict[str, str] = {}  # 会话名 → 上次行指纹
    last_beat = time.time()

    # 启动自检：立即读一次会话列表，方便确认 OCR 是否捕捉到目标会话
    try:
        rows0 = _screen_rows(cfg)
        print(f"[自检] 会话列表共读到 {len(rows0)} 行：")
        for r in rows0[:12]:
            hit = any(t.lower() in r["name"].lower() for t in cfg.target_contacts)
            flag = "★命中" if hit else "     "
            print(f"[自检]   {flag} name={r['name']!r}  text={r['text']!r}")
        hits = [r["name"] for r in _match_target_rows(rows0, cfg)]
        print(f"[自检] 命中目标(李/K)的会话: {hits or '无'}")
        if not rows0:
            print("[提示] 列表没读到文字：请确认微信窗口在屏幕前、停在会话列表页，")
            print("      且校准区域确实框住了左侧列表栏。")
        elif not hits:
            print("[提示] 当前可见列表里没有命中目标，请确认 李/K 的会话在列表可见位置。")
    except Exception as e:
        print(f"[自检失败] {e}")

    try:
        while True:
            time.sleep(cfg.poll_interval)

            rows = _screen_rows(cfg)
            matched = _match_target_rows(rows, cfg)

            # 只对命中行做差异检测：指纹变化 = 有新动态
            # 前提是该会话之前已进入过快照(已建立基准)，避免启动初期把历史当新消息
            changed = [
                r for r in matched
                if r["name"] in snapshot
                and snapshot[r["name"]] != _fingerprint(r["text"])
            ]
            for r in matched:
                snapshot[r["name"]] = _fingerprint(r["text"])

            if changed:
                row = changed[0]
                print(f"[变更] {len(changed)} 个目标会话有变化，先处理 '{row['name']}'")
                _handle_contact(cfg, responder, sender, row, store)
                time.sleep(cfg.poll_interval)  # 处理完先观察一轮
                # 期间我方发送会刷新该会话列表预览，重新拍照吸收，避免误重复
                rows2 = _screen_rows(cfg)
                for r in _match_target_rows(rows2, cfg):
                    snapshot[r["name"]] = _fingerprint(r["text"])
                last_beat = time.time()
                continue

            # 无变化：定期打心跳，方便确认程序活着
            if time.time() - last_beat >= BEAT_INTERVAL:
                print(f"[心跳] 无新变化，继续等待目标会话(李/K)来消息…")
                last_beat = time.time()
    except KeyboardInterrupt:
        print("\n已停止")
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"\n异常退出: {e}")


if __name__ == "__main__":
    main()
