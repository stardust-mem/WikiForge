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

WIKI_GENERATE_SYSTEM = """You are a wiki maintainer. Here are the wiki conventions:

{claude_md_content}

You must follow these conventions when generating wiki pages.

知识编译原则（分层策略）：
Wiki 是一个知识编译器，不同类型的页面对 LLM 知识的使用有不同要求：
- source_page（文档摘要）：严格限于原文，只提取和结构化，不添加原文没有的信息
- entity_pages（实体）：基于源文档综合，多份文档提到同一实体时合并信息，但事实必须有源文档支撑
- concept_pages（概念）：允许基于源文档内容进行解释和关联，可以用更好的结构和措辞重新组织，帮助读者理解概念
- updates（已有页面更新）：将新旧信息综合为连贯的内容，形成不断演化的知识综合

对于所有页面：具体数据、事实、引言必须来自原文，不要编造不存在的数据点。

输出严格 JSON 格式（{schema}）：
{{
  "source_page": {{
    "filename": "source-xxx.md",
    "title": "文档标题",
    "content": "完整的 markdown 内容"
  }},
  "concept_pages": [
    {{
      "filename": "concept-name.md",
      "title": "概念名称",
      "category": "concepts",
      "content": "markdown 内容"
    }}
  ],
  "entity_pages": [
    {{
      "filename": "entity-name.md",
      "title": "实体名称",
      "category": "entities",
      "content": "markdown 内容"
    }}
  ],
  "updates": [
    {{
      "page_id": "concepts/existing-page",
      "action": "merge",
      "new_content": "the full rewritten page content with new info merged"
    }}
  ]
}}

Wiki 页面规范：
- 每个页面以 YAML frontmatter 开头（title, category, source_refs, topic_tags）
- 使用 [[category/page-name]] 语法链接到其他页面
- source_page 是原始文档的**详细结构化摘要**，放在 sources/ 目录
  - 必须完整保留原文的所有关键数据、公式、表格、代码、技术细节
  - 按原文结构组织，使用标题、列表、表格使内容结构化
  - 不要过度压缩，宁可多保留细节也不要遗漏重要信息
  - 对原文中的图片引用可以用文字描述替代
- concept_pages 提取文档中的核心概念（1-3个），放在 concepts/ 目录
  - 概念页是独立的知识单元，可以被多个文档引用
  - 基于源文档内容，用清晰的结构解释概念，帮助读者理解
  - 可以建立概念间的关联（通过 wikilink），但核心事实须来自源文档
- entity_pages 提取重要实体（人/组织/产品），放在 entities/ 目录
- 如果新文档的内容与 index 中已有的页面相关，使用 updates 列表指定对已有页面的更新
- updates 中的 new_content 应该是完整的重写内容（包含旧信息和新信息的合并）
- 如果没有需要更新的已有页面，updates 可以为空列表"""

WIKI_GENERATE_USER = """Here is the current wiki index:

{index_content}

根据以下文档信息生成 Wiki 页面（包括新页面和对已有页面的更新）：

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
