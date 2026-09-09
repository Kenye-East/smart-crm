"""文本切分器：递归字符切分 + 重叠"""

import hashlib

from .base import Chunk, Document


def _make_chunk_id(source: str, content: str) -> str:
    """生成确定性 chunk ID（sha256 前 32 位格式化为 UUID）"""
    raw = f"{source}:{content}".encode("utf-8")
    hex32 = hashlib.sha256(raw).hexdigest()[:32]
    # 格式化为 UUID: 8-4-4-4-12
    return f"{hex32[0:8]}-{hex32[8:12]}-{hex32[12:16]}-{hex32[16:20]}-{hex32[20:32]}"


class RecursiveCharacterTextSplitter:
    """
    递归字符切分器

    按分隔符优先级递归切分，保证每个 chunk 不超过 chunk_size，
    相邻 chunk 之间有 overlap 重叠。
    """

    # 分隔符优先级（从高到低）
    DEFAULT_SEPARATORS = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
        separators: list[str] | None = None,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or self.DEFAULT_SEPARATORS

    def split_documents(self, documents: list[Document]) -> list[Chunk]:
        """将文档列表切分为 Chunk 列表"""
        chunks: list[Chunk] = []
        for doc in documents:
            chunks.extend(self._split_document(doc))
        return chunks

    def _split_document(self, document: Document) -> list[Chunk]:
        """切分单个文档"""
        text_chunks = self._split_text(document.content)
        chunks: list[Chunk] = []
        for idx, text in enumerate(text_chunks):
            chunks.append(
                Chunk(
                    chunk_id=_make_chunk_id(document.source, text),
                    source=document.source,
                    content=text,
                    chunk_index=idx,
                    metadata={
                        "filename": document.metadata.get("filename"),
                        "total_chunks": len(text_chunks),
                    },
                )
            )
        return chunks

    def _split_text(self, text: str) -> list[str]:
        """递归切分文本"""
        return self._recursive_split(text, self.separators)

    def _recursive_split(self, text: str, separators: list[str]) -> list[str]:
        if not text:
            return []

        # 找到第一个能切分文本的分隔符
        separator = separators[-1]  # 默认最后一个（空字符）
        new_separators: list[str] = []
        for i, sep in enumerate(separators):
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                new_separators = separators[i + 1 :]
                break

        # 按分隔符切分
        splits = text.split(separator) if separator else list(text)

        # 合并小块，确保不超过 chunk_size
        merged: list[str] = []
        current = ""
        for piece in splits:
            if not piece:
                continue
            candidate = (current + separator + piece) if current else piece
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    merged.append(current)
                # 如果单个 piece 就超过 chunk_size，递归用更细的分隔符
                if len(piece) > self.chunk_size and new_separators:
                    sub_splits = self._recursive_split(piece, new_separators)
                    merged.extend(sub_splits)
                else:
                    current = piece
        if current:
            merged.append(current)

        # 添加重叠
        if self.chunk_overlap > 0 and len(merged) > 1:
            merged = self._add_overlap(merged)

        return merged

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        """为相邻 chunk 添加重叠"""
        result: list[str] = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                result.append(chunk)
                continue
            prev = chunks[i - 1]
            # 取前一个 chunk 的末尾作为重叠
            overlap_text = prev[-self.chunk_overlap :] if len(prev) > self.chunk_overlap else prev
            result.append(overlap_text + chunk)
        return result
