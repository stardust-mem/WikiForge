"""MD / TXT 文档提取"""

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MarkdownExtractResult:
    text: str
    headings: list[dict]  # [{"level": 1, "text": "...", "char_offset": 0}]
    image_paths: list[str]  # 本地/远程图片路径


def extract_markdown(file_path: Path) -> MarkdownExtractResult:
    """
    提取 MD/TXT 内容：
    - 直接读取文本
    - 识别 Heading 结构
    - 识别内嵌图片链接 ![](path)
    """
    text = file_path.read_text(encoding="utf-8")

    # 提取 headings
    headings = []
    char_offset = 0
    for line in text.split("\n"):
        match = re.match(r"^(#{1,6})\s+(.+)", line)
        if match:
            level = len(match.group(1))
            headings.append({
                "level": level,
                "text": match.group(2).strip(),
                "char_offset": char_offset,
            })
        char_offset += len(line) + 1

    # 提取图片链接
    image_paths = re.findall(r"!\[.*?\]\((.+?)\)", text)

    return MarkdownExtractResult(
        text=text,
        headings=headings,
        image_paths=image_paths,
    )
