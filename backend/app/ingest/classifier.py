"""自动分类 — document_type + topic_tags + entities"""

from app.llm.router import get_provider
from app.llm.prompts import CLASSIFY_SYSTEM, CLASSIFY_USER
from app.models.schemas import ClassificationResult


async def classify_document(
    filename: str,
    content: str,
) -> ClassificationResult:
    """
    自动分类文档。

    使用 LLM 分析前 2000 字符，输出：
    - document_type: 9 种类型之一
    - topic_tags: 3-8 个中文标签
    - entities: 人名/组织/产品
    - summary_one_line: 一句话总结
    """
    provider = get_provider("classify")

    # 取前 2000 字符
    content_preview = content[:2000]

    result = await provider.chat_json(
        messages=[
            {"role": "system", "content": CLASSIFY_SYSTEM},
            {
                "role": "user",
                "content": CLASSIFY_USER.format(
                    filename=filename,
                    content_preview=content_preview,
                ),
            },
        ]
    )

    # 规范化结果
    valid_types = {
        "research_paper", "technical_doc", "meeting_notes", "report",
        "book_chapter", "slide_deck", "news_article", "note", "data_report",
    }
    doc_type = result.get("document_type", "note")
    if doc_type not in valid_types:
        doc_type = "note"

    return ClassificationResult(
        document_type=doc_type,
        confidence=float(result.get("confidence", 0.5)),
        topic_tags=result.get("topic_tags", []),
        primary_topic=result.get("primary_topic", ""),
        language=result.get("language", "zh"),
        time_period=result.get("time_period"),
        entities=result.get("entities", []),
        summary_one_line=result.get("summary_one_line", ""),
    )
