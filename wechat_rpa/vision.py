"""视觉层：截图、OCR、新消息检测

核心思路：不依赖微信 API，纯粹靠"看屏幕"。
- 定时截取聊天内容区域
- 用 RapidOCR 提取文字
- 与上一轮对比，文本新增了 → 判定对方发来新消息
"""
from __future__ import annotations

import numpy as np
import pyautogui
from PIL import Image

from .config import Region

# OCR 引擎懒加载（全局单例）
_ocr_engine = None
_ocr_loaded = False


def _get_ocr_engine():
    """获取 RapidOCR 引擎（懒加载单例）"""
    global _ocr_engine, _ocr_loaded
    if not _ocr_loaded:
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
        _ocr_loaded = True
    return _ocr_engine


def capture_region(region: Region) -> np.ndarray:
    """截取屏幕指定区域，返回 BGR ndarray"""
    img = pyautogui.screenshot(region=(region.left, region.top, region.width, region.height))
    return np.array(img)[:, :, ::-1]  # RGB → BGR


def ocr_image(image: np.ndarray) -> str:
    """OCR 识别图片文字，返回每行拼接的文本"""
    blocks = ocr_blocks(image)
    return "\n".join(b["text"] for b in blocks)


def ocr_blocks(image: np.ndarray, scale: float = 3.0) -> list[dict]:
    """OCR 并保留每个文字块坐标。

    小字(微信列表里的名字/预览)直接识别很差，先把图片放大 scale 倍再识别，
    坐标再映射回原图。置信度阈值调低，避免 K 这类单个小字母被过滤。
    返回每项:
      {text, x0,y0,x1,y1(相对原图), xc,yc(中心)}
    """
    img, factor = _upscale(image, scale)
    engine = _get_ocr_engine()
    try:
        result, _ = engine(img, text_score=0.3, box_thresh=0.2)
    except TypeError:  # 旧版本不支持调用期参数时回退
        result, _ = engine(img)
    if not result:
        return []
    blocks = []
    for item in result:
        pts = item[0]
        xs = [p[0] / factor for p in pts]
        ys = [p[1] / factor for p in pts]
        text = str(item[1]).strip()
        if not text:
            continue
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        blocks.append({
            "text": text,
            "x0": x0, "y0": y0, "x1": x1, "y1": y1,
            "xc": (x0 + x1) / 2, "yc": (y0 + y1) / 2,
        })
    return blocks


def _upscale(image: np.ndarray, factor: float) -> tuple[np.ndarray, float]:
    """把 BGR 图放大 factor 倍返回 (放大图, factor)；factor<=1 时原样返回。"""
    if factor <= 1.0:
        return image, 1.0
    h, w = image.shape[:2]
    pil = Image.fromarray(image[:, :, ::-1])  # BGR -> RGB
    pil = pil.resize((int(round(w * factor)), int(round(h * factor))), Image.LANCZOS)
    arr = np.array(pil)[:, :, ::-1]  # RGB -> BGR
    return arr, factor


def group_into_rows(blocks: list[dict], y_tol: float = 26.0) -> list[dict]:
    """把文字块按垂直位置聚合成"视觉行"（用于会话列表等行式布局）。

    y_tol = 同行内允许的 y0 差；相邻会话行间距一般 >50，不会误并。
    每行: {text(按 x 从左到右拼), name(最左块文本), x0,y0,x1,y1,xc,yc}
    """
    if not blocks:
        return []
    rows: list[dict] = []
    for b in sorted(blocks, key=lambda b: (b["y0"], b["x0"])):
        for row in rows:
            if abs(b["y0"] - row["y0"]) <= y_tol:
                row["blocks"].append(b)
                break
        else:
            rows.append({"y0": b["y0"], "blocks": [b]})

    out = []
    for row in rows:
        bs = sorted(row["blocks"], key=lambda b: b["x0"])
        top_y = min(b["y0"] for b in bs)
        # 名字在最上面一条带（与时间同高），预览在下方另一条带
        name_band = [b for b in bs if b["y0"] - top_y <= 14]
        name_cands = [b for b in name_band if not b["text"].isdigit()]
        name = (name_cands or name_band or bs)[0]["text"]
        out.append({
            "text": " ".join(b["text"] for b in bs),
            "name": name,
            "x0": min(b["x0"] for b in bs),
            "y0": min(b["y0"] for b in bs),
            "x1": max(b["x1"] for b in bs),
            "y1": max(b["y1"] for b in bs),
            "xc": (min(b["x0"] for b in bs) + max(b["x1"] for b in bs)) / 2,
            "yc": (min(b["y0"] for b in bs) + max(b["y1"] for b in bs)) / 2,
        })
    return sorted(out, key=lambda r: r["y0"])


def refine_name_from_strip(image: np.ndarray, row: dict, scale: float = 4.0) -> str:
    """对该行顶部"名字条"小区域裁切并 4 倍放大单独 OCR，纠正首遍漏掉的名字。

    用于首遍整图 OCR 没认出名字（如单个字母 K）的行。
    返回纠正后的名字；读不到则返回空串（调用方保留原名）。
    """
    h, w = image.shape[:2]
    x0 = max(int(row["x0"]) - 2, 0)
    x1 = min(int(row["x0"] + (row["x1"] - row["x0"]) * 0.7), w)
    y0 = max(int(row["y0"]) - 4, 0)
    y1 = min(int(row["y0"]) + 26, h)
    if x1 - x0 < 8 or y1 - y0 < 8:
        return ""
    strip = image[y0:y1, x0:x1]
    blocks = ocr_blocks(strip, scale=scale)
    blocks = [b for b in blocks if not b["text"].isdigit()]
    if not blocks:
        return ""
    return min(blocks, key=lambda b: b["x0"])["text"]


class NewMessageDetector:
    """
    新消息检测器：基于文本变化的循环对比。

    维护上一轮 OCR 文本，与当前对比，提取"新增的行"。
    """

    def __init__(self, region: Region, threshold: int = 30):
        self.region = region
        self.threshold = threshold
        self._prev_lines: list[str] = []  # 上一轮完整文本行

    def snap_and_diff(self) -> tuple[dict, bool]:
        """
        截图 + OCR + 对比。

        Returns:
            (info, has_new)
            info: dict，含 current_lines, new_lines
            has_new: 是否有新增内容且增量达到阈值
        """
        image = capture_region(self.region)
        text = ocr_image(image)
        current_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # 求新增行：本轮有、上一轮没有的
        prev_set = set(self._prev_lines)
        new_lines = [ln for ln in current_lines if ln not in prev_set]

        has_new = len("".join(new_lines)) >= self.threshold

        # 本轮作为下一轮的基准
        self._prev_lines = current_lines

        return {"current_lines": current_lines, "new_lines": new_lines}, has_new

    def reset_baseline(self):
        """把当前屏幕内容设为基准，丢弃累积的差异。

        发送回复后调用，避免把自己刚发出的消息误判为新消息。
        """
        self._prev_lines = []
        image = capture_region(self.region)
        text = ocr_image(image)
        self._prev_lines = [ln.strip() for ln in text.splitlines() if ln.strip()]


def pixel_diff(a: np.ndarray, b: np.ndarray) -> float:
    """两张图差异比例（0~1）。辅助判断有无变化，供调试用"""
    if a.shape != b.shape:
        return 1.0
    diff = np.mean(np.abs(a.astype(int) - b.astype(int)))
    return float(diff / 255.0)