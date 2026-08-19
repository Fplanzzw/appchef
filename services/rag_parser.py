"""RAG 文档解析服务"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from docx import Document
except ImportError:
    Document = None

try:
    import docx2txt
except ImportError:
    docx2txt = None

try:
    import docx
except ImportError:
    python_docx = None

logger = logging.getLogger(__name__)


def parse_document(file_path: str, file_type: str) -> str:
    """解析文档，返回纯文本。

    Args:
        file_path: 文件路径
        file_type: 文件类型（pdf/doc/docx/txt/word）

    Returns:
        文档文本内容
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    file_type = file_type.lower()

    if file_type == "pdf":
        return _parse_pdf(file_path)
    elif file_type in ["doc", "docx", "word"]:
        return _parse_docx(file_path)
    elif file_type == "txt":
        return _parse_txt(file_path)
    else:
        raise ValueError(f"不支持的文件类型: {file_type}")


def _parse_pdf(file_path: str) -> str:
    """解析 PDF 文件"""
    if PdfReader is None:
        raise ImportError("请安装 pypdf 库: pip install pypdf")

    reader = PdfReader(file_path)
    text_parts = []

    for page in reader.pages:
        try:
            text = page.extract_text()
            if text:
                text_parts.append(text)
        except Exception as e:
            logger.warning(f"解析 PDF 页面失败: {e}")

    return "\n".join(text_parts)


def _parse_docx(file_path: str) -> str:
    """解析 Word 文件"""
    if Document is None:
        raise ImportError("请安装 python-docx 库: pip install python-docx")

    try:
        # 尝试使用python-docx
        doc = Document(file_path)
        text_parts = []
        for paragraph in doc.paragraphs:
            if paragraph.text:
                text_parts.append(paragraph.text)
        return "\n".join(text_parts)
    except Exception as e:
        logger.warning(f"使用python-docx解析Word文件失败: {e}")
        try:
            # 尝试使用docx2txt作为备选方案
            if docx2txt is not None:
                return docx2txt.process(file_path)
            else:
                raise ImportError("请安装 docx2txt 库: pip install docx2txt")
        except Exception as e2:
            logger.error(f"使用docx2txt解析Word文件也失败: {e2}")
            raise ImportError("无法解析Word文件，请确保安装了python-docx或docx2txt库")


def _parse_txt(file_path: str) -> str:
    """解析纯文本文件"""
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def split_text_into_chunks(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> List[str]:
    """将文本切分成小块。

    Args:
        text: 输入文本
        chunk_size: 每块大小（字符数）
        overlap: 块之间重叠大小

    Returns:
        文本块列表
    """
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size

        # 如果不是最后一块，尝试在句子边界切分
        if end < text_len:
            # 查找最后一个句子结束符号
            for delimiter in ["。", "！", "？", "\n", ".", "!", "?"]:
                last_pos = text.rfind(delimiter, start, end)
                if last_pos != -1:
                    end = last_pos + 1
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap if end < text_len else end

    return chunks