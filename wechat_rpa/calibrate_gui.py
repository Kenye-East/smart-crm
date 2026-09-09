"""微信 RPA - 图形化屏幕校准工具

分两个阶段：
  阶段0（引导小窗）：先让用户把微信窗口调到最前面（浮起）、选好要自动
     回复的联系人会话；准备好后点「开始校准」才进入框选。避免微信被
     全屏遮罩挡住无法操作的问题。
  阶段1（全屏框选）：对"当前屏幕截图"依次框选——
    1. 会话列表区域（左侧联系人栏）
    2. 聊天内容区域（右侧消息区）
    3. 输入框位置（单击一个点，自动保存完成）
完成后写入 calibrated.json，config.py 会优先读取它。

返回约定：
    run_calibration_gui() -> bool    True=成功保存；False=用户取消/未完成

用法：
    python -m wechat_rpa.calibrate_gui
"""
from __future__ import annotations

import ctypes
import json
import time
import tkinter as tk
from pathlib import Path

import pyautogui
from PIL import ImageTk

# 校准结果文件（与 config.py 同目录）
CALIB_FILE = Path(__file__).with_name("calibrated.json")

# 步骤说明
STEPS = [
    "会话列表区域：请用鼠标框住【左侧联系人栏】",
    "聊天内容区域：请用鼠标框住【右侧消息区】",
    "输入框位置：请在【聊天输入框】上单击一下",
]

# 每步底部操作提示
STEP_HINTS = [
    "在左侧联系人栏 按住左键拖出矩形，松手后再点右上角「下一步」",
    "在右侧消息区 按住左键拖出矩形，松手后再点右上角「下一步」",
    "在聊天输入框内 单击一下即可完成（自动保存并关闭，无需点「下一步」）",
]

# 前两步对应的配置键（第 3 步是单击点，单独处理）
REGION_KEYS = ("chat_list_region", "chat_content_region")

# 引导窗文案
INTRO_TEXT = (
    "校准前准备：\n\n"
    "1. 点一下任务栏的微信图标或微信窗口，让微信浮到最前面；\n"
    "2. 把微信窗口停在你希望的位置（建议最大化），并点开\n"
    "    要自动回复的联系人会话（如「李」）；\n"
    "3. 保持微信位置不动，点下方「开始校准」。\n\n"
    "之后只需依次框选：左侧联系人栏 → 右侧消息区 → 单击输入框。\n"
    "框选及运行期间请勿移动微信窗口。"
)


def _enable_dpi_awareness() -> None:
    """让进程 DPI-aware，统一 Tk 与 pyautogui 的像素坐标（高分屏必备）"""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


_enable_dpi_awareness()


class Calibrator(tk.Tk):
    """引导小窗 + 全屏框选校准器。mainloop 结束后看 self.finished 判断是否完成。"""

    def __init__(self):
        super().__init__()
        self.title("微信 RPA - 屏幕校准")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        self.finished = False  # 是否成功保存校准文件

        # 阶段0：引导小窗
        self._build_intro()
        self._center_intro()

    # ---------- 阶段0：引导 ----------
    def _build_intro(self):
        frame = tk.Frame(self, padx=28, pady=20)
        frame.pack(fill="both", expand=True)

        tk.Label(
            frame, text="屏幕校准 - 准备",
            font=("Microsoft YaHei", 16, "bold"), anchor="w",
        ).pack(fill="x")
        tk.Label(
            frame, text=INTRO_TEXT, justify="left", anchor="w",
            wraplength=620, font=("Microsoft YaHei", 11), fg="#333333",
        ).pack(fill="x", pady=(14, 4))

        btns = tk.Frame(frame)
        btns.pack(fill="x", pady=(18, 0))
        tk.Button(
            btns, text="取消", command=self._cancel,
            width=10, font=("Microsoft YaHei", 11),
        ).pack(side="right", padx=(0, 10))
        start_btn = tk.Button(
            btns, text="开始校准", command=self._start_calibration,
            width=12, font=("Microsoft YaHei", 12), default="active",
        )
        start_btn.pack(side="right")
        start_btn.focus_force()

        self.protocol("WM_DELETE_WINDOW", self._cancel)

    def _center_intro(self):
        self.update_idletasks()
        w = max(self.winfo_reqwidth(), 620)
        h = max(self.winfo_reqheight(), 320)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max((sw - w) // 2, 0)
        y = max((sh - h) // 2 - 40, 0)
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ---------- 进入阶段1：全屏框选 ----------
    def _start_calibration(self):
        # 先隐藏引导窗再截图，保证截图里只有用户布置好的微信/桌面
        self.withdraw()
        self.update()
        time.sleep(0.35)  # 等窗口真正从合成画面消失

        self.sw, self.sh = pyautogui.size()
        bg = pyautogui.screenshot()
        self._bg_photo = ImageTk.PhotoImage(bg)

        # 切到全屏无边框置顶
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.geometry(f"{self.sw}x{self.sh}+0+0")

        # 清掉引导控件，换画布
        for w in list(self.winfo_children()):
            w.destroy()

        self.canvas = tk.Canvas(self, highlightthickness=0, cursor="cross")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_image(0, 0, image=self._bg_photo, anchor="nw")

        self.step = 0
        self.results: dict = {}
        self._start = None
        self._rect_id = None

        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

        self._build_overlay_buttons()
        self._draw_hint()

        self.deiconify()
        self.lift()
        self.focus_force()
        print("\n[校准] 已进入框选模式，请按屏幕顶部提示依次框选三个区域。")

    def _build_overlay_buttons(self):
        """全屏遮罩右上角控制按钮"""
        bx = self.sw - 160
        tk.Button(
            self, text="下一步", command=self._next, width=9,
            font=("Microsoft YaHei", 11),
        ).place(x=bx, y=62)
        tk.Button(
            self, text="重画", command=self._redo, width=9,
            font=("Microsoft YaHei", 11),
        ).place(x=bx, y=102)
        tk.Button(
            self, text="返回准备", command=self._back_to_intro, width=9,
            font=("Microsoft YaHei", 11),
        ).place(x=bx, y=142)
        tk.Button(
            self, text="取消", command=self._cancel, width=9,
            font=("Microsoft YaHei", 11),
        ).place(x=bx, y=182)

    def _back_to_intro(self):
        """从框选回到引导窗（比如发现微信没置前 / 截图不对）"""
        self.withdraw()
        self.overrideredirect(False)
        self.resizable(False, False)
        self.attributes("-topmost", True)
        for w in list(self.winfo_children()):
            w.destroy()
        self.canvas = None
        self._bg_photo = None
        self._build_intro()
        self._center_intro()
        self.deiconify()
        self.lift()

    # ---------- 提示绘制 ----------
    def _draw_hint(self):
        """重绘顶部步骤条与底部操作提示"""
        self.canvas.delete("hint")
        self.canvas.delete("flash")
        self.canvas.create_rectangle(0, 0, self.sw, 56, fill="#202020", tags="hint")
        self.canvas.create_text(
            self.sw // 2, 28,
            text=f"步骤 {self.step + 1}/3: {STEPS[self.step]}",
            fill="white", font=("Microsoft YaHei", 15, "bold"), tags="hint",
        )
        self.canvas.create_text(
            self.sw // 2, self.sh - 24,
            text=STEP_HINTS[self.step],
            fill="#F0F0F0", font=("Microsoft YaHei", 13), tags="hint",
        )

    def _flash(self, msg: str):
        """在底部临时显示一条黄色警示，几秒后消失"""
        self.canvas.delete("flash")
        self.canvas.create_text(
            self.sw // 2, self.sh - 60,
            text=msg, fill="#FFD54A",
            font=("Microsoft YaHei", 13, "bold"), tags="flash",
        )
        self.after(3000, lambda: self.canvas.delete("flash"))

    # ---------- 拖框交互 ----------
    def _on_press(self, event):
        self._start = (event.x, event.y)
        if self._rect_id:
            self.canvas.delete(self._rect_id)
            self._rect_id = None

    def _on_drag(self, event):
        if not self._start:
            return
        x0, y0 = self._start
        x1, y1 = event.x, event.y
        if self._rect_id:
            self.canvas.delete(self._rect_id)
        self._rect_id = self.canvas.create_rectangle(
            x0, y0, x1, y1, outline="#FF4D4F", width=3,
        )

    def _on_release(self, event):
        if not self._start:
            return
        x0, y0 = self._start
        x1, y1 = event.x, event.y
        self._start = None

        # 单击（几乎没拖动）→ 视作点选，仅用于输入框步骤
        if abs(x1 - x0) < 5 and abs(y1 - y0) < 5:
            if self.step == 2:
                self.results["input_box_pos"] = [event.x, event.y]
                self._finish()
            return

        if self.step == 0:
            self.results[REGION_KEYS[0]] = _norm_rect(x0, y0, x1, y1)
        elif self.step == 1:
            self.results[REGION_KEYS[1]] = _norm_rect(x0, y0, x1, y1)

    # ---------- 流程控制 ----------
    def _next(self):
        if self.step < 2:
            key = REGION_KEYS[self.step]
            if key not in self.results:
                self._flash("还没框出区域：请在屏幕上按住左键拖出矩形")
                return
            self.step += 1
            self._clear_drawings()
            self._draw_hint()
        else:
            if "input_box_pos" not in self.results:
                self._flash("最后一步：请在【聊天输入框】上单击一下，即自动保存完成")
                return
            self._finish()

    def _redo(self):
        key = {0: REGION_KEYS[0], 1: REGION_KEYS[1], 2: "input_box_pos"}.get(self.step)
        if key:
            self.results.pop(key, None)
        self._clear_drawings()

    def _clear_drawings(self):
        if self._rect_id:
            self.canvas.delete(self._rect_id)
            self._rect_id = None

    # ---------- 完成 / 取消 ----------
    def _finish(self):
        keys = ("chat_list_region", "chat_content_region", "input_box_pos")
        if not all(k in self.results for k in keys):
            return
        data = {k: self.results[k] for k in keys}
        CALIB_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n[校准完成] 已保存到: {CALIB_FILE}")
        print(json.dumps(data, ensure_ascii=False, indent=2))
        self.finished = True
        self.destroy()

    def _cancel(self):
        """用户取消：finished 保持 False，调用方据此退出而不是重新走流程"""
        if not self.finished:
            print("\n[校准已取消] 未生成校准文件。")
        self.destroy()


def _norm_rect(x0, y0, x1, y1) -> dict:
    """矩形坐标规范为 left/top/width/height"""
    left, right = sorted((x0, x1))
    top, bottom = sorted((y0, y1))
    return {"left": left, "top": top, "width": right - left, "height": bottom - top}


def has_calibration() -> bool:
    return CALIB_FILE.exists()


def run_calibration_gui() -> bool:
    """启动校准 GUI（阻塞直到完成）。返回 True=成功保存；False=取消/未完成。"""
    app = Calibrator()
    app.mainloop()
    return bool(getattr(app, "finished", False))


if __name__ == "__main__":
    ok = run_calibration_gui()
    if not ok:
        print("已取消校准，程序退出。")
        raise SystemExit(1)
