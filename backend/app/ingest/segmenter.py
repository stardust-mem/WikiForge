"""智能文档分段 — 三级递进策略"""

import uuid
from typing import Optional

from app.llm.router import get_provider
from app.llm.prompts import SEGMENT_SYSTEM, SEGMENT_USER
from app.models.schemas import Segment


def _estimate_tokens(text: str) -> int:
    """粗略估算 token 数（中文约 1.5 字符/token，英文约 4 字符/token）"""
    chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


def _try_structural_split(
    text: str, headings: list[dict]
) -> Optional[list[Segment]]:
    """
    第一级：结构检测。
    如果 Heading 覆盖了 80% 以上内容，按 Heading 切分。
    """
    if not headings or len(headings) < 2:
        return None

    # 检查 Heading 覆盖率：Heading 之间的文本应覆盖大部分内容
    total_len = len(text)
    covered = 0
    for i, h in enumerate(headings):
        start = h["char_offset"]
        end = headings[i + 1]["char_offset"] if i + 1 < len(headings) else total_len
        segment_len = end - start
        if segment_len > 0:
            covered += segment_len

    coverage = covered / total_len if total_len > 0 else 0
    if coverage < 0.8:
        return None

    # 按 Heading 切分
    segments = []
    for i, h in enumerate(headings):
        start = h["char_offset"]
        end = headings[i + 1]["char_offset"] if i + 1 < len(headings) else total_len
        content = text[start:end].strip()
        if not content:
            continue
        segments.append(Segment(
            segment_id=str(uuid.uuid4())[:8],
            title=h["text"],
            summary=None,
            content=content,
            token_count=_estimate_tokens(content),
        ))

    return segments if segments else None


async def _llm_semantic_split(text: str) -> list[Segment]:
    """
    第二级：LLM 语义分段。
    使用滑动窗口，让 LLM 识别主题转换点。
    """
    provider = get_provider("segment")

    # 如果文本不长，直接整体分析
    if _estimate_tokens(text) <= 3000:
        result = await provider.chat_json(
            messages=[
                {"role": "system", "content": SEGMENT_SYSTEM},
                {"role": "user", "content": SEGMENT_USER.format(text=text)},
            ]
        )
        segments = []
        for seg_data in result.get("segments", []):
            start = seg_data.get("start_char", 0)
            end = seg_data.get("end_char", len(text))
            content = text[start:end].strip()
            if content:
                segments.append(Segment(
                    segment_id=str(uuid.uuid4())[:8],
                    title=seg_data.get("title", ""),
                    summary=seg_data.get("summary", ""),
                    content=content,
                    token_count=_estimate_tokens(content),
                ))
        return segments if segments else [_whole_doc_segment(text)]

    # 长文本：滑动窗口
    window_size = 4000  # 字符
    overlap = 400
    segments = []
    pos = 0

    while pos < len(text):
        end = min(pos + window_size, len(text))
        chunk = text[pos:end]

        result = await provider.chat_json(
            messages=[
                {"role": "system", "content": SEGMENT_SYSTEM},
                {"role": "user", "content": SEGMENT_USER.format(text=chunk)},
            ]
        )

        for seg_data in result.get("segments", []):
            start_char = seg_data.get("start_char", 0) + pos
            end_char = seg_data.get("end_char", len(chunk)) + pos
            content = text[start_char:end_char].strip()
            if content and _estimate_tokens(content) > 50:
                segments.append(Segment(
                    segment_id=str(uuid.uuid4())[:8],
                    title=seg_data.get("title", ""),
                    summary=seg_data.get("summary", ""),
                    content=content,
                    token_count=_estimate_tokens(content),
                ))

        pos = end - overlap

    # 合并重叠段落（简单去重：如果两段内容重叠超过 50%，保留较长的）
    if len(segments) > 1:
        segments = _merge_overlapping(segments)

    return segments if segments else [_whole_doc_segment(text)]


def _whole_doc_segment(text: str) -> Segment:
    """整个文档作为一个段落"""
    return Segment(
        segment_id=str(uuid.uuid4())[:8],
        title="全文",
        summary=None,
        content=text,
        token_count=_estimate_tokens(text),
    )


def _merge_overlapping(segments: list[Segment]) -> list[Segment]:
    """合并重叠度过高的相邻段落"""
    merged = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        # 简单判断：如果当前段的开头 200 字符在上一段结尾出现，认为重叠
        overlap_text = seg.content[:200]
        if overlap_text in prev.content:
            # 合并：保留上一段，跳过当前重叠段
            # 但追加当前段不重叠的部分
            overlap_pos = prev.content.find(overlap_text)
            new_content = prev.content + seg.content[len(overlap_text):]
            merged[-1] = Segment(
                segment_id=prev.segment_id,
                title=prev.title,
                summary=prev.summary,
                content=new_content,
                token_count=_estimate_tokens(new_content),
            )
        else:
            merged.append(seg)
    return merged


async def _split_long_segments(segments: list[Segment]) -> list[Segment]:
    """第三级：对超过 3000 tokens 的段落递归拆分"""
    result = []
    for seg in segments:
        if seg.token_count > 3000:
            sub_segments = await _llm_semantic_split(seg.content)
            for sub in sub_segments:
                sub.parent_segment_id = seg.segment_id
            result.extend(sub_segments)
        else:
            result.append(seg)
    return result


async def segment_document(
    text: str,
    headings: Optional[list[dict]] = None,
) -> list[Segment]:
    """
    智能文档分段入口。

    三级递进策略：
    1. 结构检测（Heading 覆盖率 >= 80%）
    2. LLM 语义分段
    3. 超长段落递归拆分
    """
    # 第一级：尝试结构化切分
    if headings:
        structural = _try_structural_split(text, headings)
        if structural:
            # 对超长段落做二次拆分
            return await _split_long_segments(structural)

    # 第二级：LLM 语义分段
    segments = await _llm_semantic_split(text)

    # 第三级：超长段落递归拆分
    return await _split_long_segments(segments)
