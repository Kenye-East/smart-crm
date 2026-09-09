"""文档加载器：从文件系统加载并提取纯文本"""

import os
from pathlib import Path

from bs4 import BeautifulSoup

from .base import Document

# 支持的文件扩展名
SUPPORTED_EXTENSIONS = {".txt", ".md", ".html", ".htm", ".pdf"}

# PDF 渲染 DPI（仅扫描版 OCR 时使用）
PDF_OCR_DPI = 200


def load_documents(directory: str | os.PathLike) -> list[Document]:
    """
    加载目录下所有支持的文档

    Args:
        directory: 文档目录路径

    Returns:
        Document 列表
    """
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"目录不存在: {directory}")

    documents: list[Document] = []
    for file_path in sorted(directory.iterdir()):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        content, pdf_method = _extract_text(file_path)
        if not content.strip():
            continue

        documents.append(
            Document(
                source=str(file_path),
                content=content,
                metadata={
                    "filename": file_path.name,
                    "extension": file_path.suffix.lower(),
                    "size": file_path.stat().st_size,
                    "pdf_method": pdf_method,  # None | "text" | "ocr"
                },
            )
        )

    return documents


def _extract_text(file_path: Path) -> tuple[str, str | None]:
    """根据文件类型提取纯文本，返回 (文本, pdf 提取方式)"""
    suffix = file_path.suffix.lower()

    if suffix in (".html", ".htm"):
        return _extract_html(file_path), None
    elif suffix == ".pdf":
        return _extract_pdf(file_path)
    else:
        # .txt, .md 等纯文本
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        return text, None


def _extract_html(file_path: Path) -> str:
    """从 HTML 中提取纯文本（去除标签、脚本、样式）"""
    html = file_path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "lxml")

    # 移除 script 和 style
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    # 清理多余空行
    lines = [line.strip() for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    return text


# OCR 引擎懒加载（全局单例，首次使用才初始化）
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


def _extract_pdf(file_path: Path) -> tuple[str, str]:
    """
    从 PDF 提取纯文本

    策略：逐页用 PyMuPDF 提取文字层；
    若整页无文字（扫描版），渲染成图片后走 RapidOCR。

    Returns:
        (文本, 提取方式): "text" 表示有文字层，走 OCR 的页以 (方式) 拼接
    """
    import pymupdf

    doc = pymupdf.open(file_path)
    try:
        pages: list[str] = []
        used_ocr = False

        for page in doc:
            text = page.get_text().strip()
            if text:
                pages.append(text)
                continue

            # 无文字层 → OCR 识别
            used_ocr = True
            pix = page.get_pixmap(dpi=PDF_OCR_DPI)
            image_bytes = pix.tobytes("png")
            ocr_text = _ocr_image(image_bytes)
            if ocr_text:
                pages.append(ocr_text)

        content = "\n\n".join(pages)
        method = "ocr" if used_ocr else "text"
        return content, method
    finally:
        doc.close()


def _ocr_image(image_bytes: bytes) -> str:
    """用 RapidOCR 识别图片中的文字"""
    import numpy as np
    import cv2

    # 解码 PNG → BGR ndarray
    nparr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    engine = _get_ocr_engine()
    result, _ = engine(image)
    if not result:
        return ""

    # result 为 [[box, text, score], ...]，按行拼接
    lines = [str(item[1]) for item in result]
    return "\n".join(lines)
