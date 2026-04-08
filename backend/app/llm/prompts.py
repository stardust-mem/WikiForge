"""Prompt 模板管理"""

CLASSIFY_SYSTEM = """你是一个文档分类专家。分析用户提供的文档内容，输出分类结果。

输出严格 JSON 格式：
{
  "document_type": "research_paper|technical_doc|meeting_notes|report|book_chapter|slide_deck|news_article|note|data_report",
  "confidence": 0.0-1.0,
  "topic_tags": ["标签1", "标签2"],
  "primary_topic": "最主要的主题",
  "language": "zh|en|mixed",
  "time_period": "2024-Q1 或 null",
  "entities": ["人名", "组织名", "产品名"],
  "summary_one_line": "一句话总结"
}

规则：
- topic_tags 3-8 个，使用中文
- entities 提取文档中出现的人名、组织、产品
- document_type 必须是列表中的值之一"""

CLASSIFY_USER = """分析以下文档内容并分类：

文档名：{filename}
内容（前 2000 字符）：
{content_preview}"""

SEGMENT_SYSTEM = """你是一个文档结构分析专家。你的任务是识别文档中的主题转换点，将文档分成语义连贯的段落。

输出严格 JSON 格式：
{
  "segments": [
    {
      "start_char": 0,
      "end_char": 1500,
      "title": "段落推断标题",
      "summary": "一句话概括本段内容"
    }
  ]
}

规则：
- 每段应该是一个语义完整的单元
- 不要在句子中间切断
- 每段建议 500-2000 字符
- title 用中文，概括本段核心内容"""

SEGMENT_USER = """识别以下文本中的主题转换点，输出分段结果：

{text}"""

WIKI_GENERATE_SYSTEM = """你是一个知识管理专家。根据用户提供的文档内容和分类信息，生成结构化的 Wiki 页面。

输出严格 JSON 格式：
{
  "source_page": {
    "filename": "source-xxx.md",
    "title": "文档标题",
    "content": "完整的 markdown 内容"
  },
  "concept_pages": [
    {
      "filename": "concept-name.md",
      "title": "概念名称",
      "category": "concepts",
      "content": "markdown 内容"
    }
  ],
  "entity_pages": [
    {
      "filename": "entity-name.md",
      "title": "实体名称",
      "category": "entities",
      "content": "markdown 内容"
    }
  ]
}

Wiki 页面规范：
- 每个页面以 YAML frontmatter 开头（title, category, source_refs, topic_tags）
- 使用 [[wikilink]] 语法链接到其他页面
- source_page 是原始文档的摘要页，放在 sources/ 目录
- concept_pages 提取文档中的核心概念（1-3个），放在 concepts/ 目录
- entity_pages 提取重要实体（人/组织/产品），放在 entities/ 目录
- 内容要精炼、结构化，不是简单复制原文"""

WIKI_GENERATE_USER = """根据以下文档信息生成 Wiki 页面：

文档名：{filename}
文档类型：{document_type}
主题标签：{topic_tags}
实体：{entities}
摘要：{summary}

文档内容：
{content}"""

VISION_CHART = """描述这张图表：
1. 图表类型（柱状图/折线图/饼图/表格等）
2. X轴和Y轴的含义
3. 关键数据点
4. 核心结论

用中文回答，简洁准确。"""

VISION_DIAGRAM = """描述这张架构图/流程图：
1. 主要组成部分
2. 各部分之间的关系和流程
3. 核心信息

用中文回答，简洁准确。"""

VISION_GENERAL = """简要描述这张图片的内容（1-2句话），用中文。"""
