# WikiForge 开源发布文案

> 项目地址：https://github.com/stardust-mem/WikiForge

---

## 微博 / 小红书 / 朋友圈

开源了一个自己做的 AI 知识管理工具——**WikiForge**

核心想法来自 Karpathy 的一篇文章：与其每次问 AI 都重新检索原文，不如让 LLM 把文档「编译」成一个持续演化的 Wiki 知识库。

你上传 PDF / PPT / Word，它自动整理成：
- sources（文档摘要）
- concepts（概念解释）
- entities（人物/产品/组织）
- topics（跨文档主题汇总）

搜索是 BM25 + 向量混合检索，还有 AI 问答、导入质量评分、Wiki 健康检查。
知识库本身是 Markdown 文件，直接用 Obsidian 打开。

本地部署，数据完全自己掌控，一条 `docker compose up` 跑起来。

GitHub：https://github.com/stardust-mem/WikiForge
欢迎 Star ⭐ 和提 Issue

---

## 知乎 / 即刻

开源了 WikiForge —— 一个把文档「编译」成结构化 Wiki 的 AI 知识管理系统。

传统 RAG 的问题是每次检索都依赖原始文档，重复计算、上下文浪费。Karpathy 提出的思路是：让 LLM 一次性将文档提炼成 Wiki，后续查询走 Wiki 而非原文。WikiForge 是这个想法的完整实现。

**核心功能：**
上传 PDF / DOCX / PPTX → LLM 自动生成四层 Wiki（sources / concepts / entities / topics）→ BM25 + 向量混合搜索 → AI 问答可归档回 Wiki。本地模型评估导入质量，防止幻觉。知识库为 Markdown，兼容 Obsidian。

Tech stack：FastAPI + React + SQLite + sentence-transformers，支持 MiniMax / DeepSeek / Ollama 等多模型接入，Docker 一键部署。

🔗 https://github.com/stardust-mem/WikiForge

---

## Twitter / X（英文）

Just open-sourced WikiForge — an AI-powered document-to-wiki compiler.

Upload PDFs, DOCX, PPTs → LLM compiles them into a structured, searchable wiki (sources / concepts / entities / topics). Hybrid BM25 + vector search, AI Q&A, Obsidian-compatible Markdown output.

Inspired by @karpathy's LLM wiki idea. Local-first, self-hosted.

⭐ https://github.com/stardust-mem/WikiForge
