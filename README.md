# WikiForge

**English** | [中文](#中文)

> An AI-powered document-to-wiki compiler inspired by Karpathy's LLM Wiki. Upload PDFs, DOCX, and PPTX — WikiForge distills them into a structured knowledge base (sources / concepts / entities / topics) with hybrid BM25 + vector search, AI Q&A, import quality evaluation, and Obsidian compatibility. Local-first, self-hosted.

---

## Features

| Feature | Description |
|---------|-------------|
| **Multi-format ingestion** | PDF, DOCX, PPTX, Markdown, TXT |
| **Structured wiki generation** | LLM compiles documents into a 4-layer wiki: sources / concepts / entities / topics |
| **Hybrid search** | BM25 full-text (SQLite FTS5) + vector semantic search, executed in parallel |
| **AI Q&A** | RAG-based answers from your wiki; good answers can be archived as new wiki pages |
| **Import quality evaluation** | Local model scores faithfulness + completeness, guards against LLM hallucination |
| **Wiki lint** | Detects broken links, orphan pages, and format issues |
| **Obsidian compatible** | Wiki files are standard Markdown + Wikilink, open directly in Obsidian |
| **Backlinks** | Every page shows all pages that link to it |
| **Deduplication** | Content-hash check prevents re-processing the same document |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Frontend  (React + Vite)                   │
│       IngestPage · WikiPage · SearchPage · LintPage          │
└──────────────────────────┬───────────────────────────────────┘
                           │ REST API
┌──────────────────────────▼───────────────────────────────────┐
│                     Backend  (FastAPI)                        │
│   /api/ingest   /api/wiki   /api/search   /api/lint          │
│                                                              │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ Ingest      │  │ Hybrid Search│  │ LLM Router       │   │
│  │ PDF·DOCX·   │  │ BM25 + Vec   │  │ cloud/local/     │   │
│  │ PPTX·MD·TXT │  │ (parallel)   │  │ vision/eval      │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│                                                              │
│   SQLite  (wiki.db)          wiki-root/  (Markdown files)   │
└──────────────────────────────────────────────────────────────┘
```

**wiki-root 4-layer structure:**
```
wiki-root/
├── CLAUDE.md      # Wiki schema (LLM instruction file)
├── index.md       # Auto-maintained content index
├── log.md         # Operation log
├── sources/       # Per-document detailed summary pages
├── entities/      # Named entity pages (products, orgs, people)
├── concepts/      # Concept pages (techniques, abstract knowledge)
└── topics/        # Topic aggregation pages (cross-document synthesis)
```

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **MiniMax API Key** | Primary LLM — [get one here](https://platform.minimaxi.com/) |
| **Python 3.11+** | Backend runtime |
| **Node.js 18+** | Frontend build |
| **Anthropic API Key** | Optional — Vision processing for image-heavy PDFs |
| **Ollama** | Optional — Local model for quality evaluation (`qwen3.5:9b`) |
| **Docker + Compose** | Optional — Recommended for one-command deployment |

> **Only a MiniMax key is required to get started.** Vision and local eval are optional.

---

## Quick Start (Docker)

### 1. Clone

```bash
git clone https://github.com/stardust-mem/WikiForge.git
cd wikiforge
```

### 2. Configure API keys

```bash
cp .env.example .env
```

Edit `.env`:

```env
MINIMAX_API_KEY=your_minimax_key_here

# Optional: Vision processing for image-heavy PDFs
ANTHROPIC_API_KEY=your_anthropic_key_here

# Optional: External access via Cloudflare Tunnel
CLOUDFLARE_TUNNEL_TOKEN=
```

### 3. Configure LLM

```bash
cp backend/config.example.yaml backend/config.yaml
```

The default config uses MiniMax for all tasks. Edit `backend/config.yaml` to change models or add providers.

### 4. Start

```bash
docker compose up -d
```

Open [http://localhost](http://localhost).

> **First launch** downloads the embedding model (`BAAI/bge-small-zh-v1.5`) and installs Python dependencies — allow a few minutes.

### Optional: External access via Cloudflare Tunnel

Set `CLOUDFLARE_TUNNEL_TOKEN` in `.env`, then:

```bash
docker compose --profile tunnel up -d
```

---

## Local Development

### Backend

```bash
cd backend

python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

pip install -r requirements.txt

cp config.example.yaml config.yaml
# Fill in your API keys in config.yaml

uvicorn app.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`. API requests are proxied to `:8000` via Vite config.

---

## LLM Configuration

`backend/config.yaml` supports multiple LLM providers:

```yaml
llm:
  # Cloud model: wiki generation, segmentation, Q&A (complex tasks)
  cloud_provider: "minimax"       # minimax / claude / deepseek / kimi / openai
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: ""               # or set via MINIMAX_API_KEY env var

  # Local model: classification, simple summarization (lightweight tasks)
  # No Ollama? Set local_* identical to cloud_* to route everything to the cloud
  local_provider: "minimax"
  local_model: "MiniMax-M2.7"
  local_api_key: ""

  # Vision model: image-heavy PDFs (requires multimodal capability)
  vision_provider: "claude"
  vision_model: "claude-sonnet-4-6"
  vision_api_key: ""              # or set via ANTHROPIC_API_KEY env var

  # Embedding model (runs locally, auto-downloaded on first start)
  embedding_model: "BAAI/bge-small-zh-v1.5"
```

**Minimal config (MiniMax only):**

```yaml
llm:
  cloud_provider: "minimax"
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: "your_key"
  local_provider: "minimax"
  local_model: "MiniMax-M2.7"
  local_api_key: "your_key"
  vision_provider: ""
  vision_api_key: ""
```

**Using DeepSeek / Kimi / any OpenAI-compatible API:**

```yaml
llm:
  cloud_provider: "deepseek"
  cloud_model: "deepseek-chat"
  cloud_api_key: "your_key"
  cloud_base_url: "https://api.deepseek.com/v1"
```

**Using Ollama for local quality evaluation:**

```bash
ollama pull qwen3.5:9b
```

```yaml
llm:
  local_provider: "ollama"
  local_model: "qwen3.5:9b"
  local_base_url: "http://localhost:11434/v1"
  local_api_key: "ollama"
```

---

## Usage

### Ingest a document

Go to **Import** → upload a file (PDF / DOCX / PPTX / MD / TXT).

WikiForge will:
1. Extract content (Vision OCR for image-heavy PDFs)
2. LLM-compile into sources / concepts / entities / topics pages
3. Update the index and search index
4. Show an import report: pages created/updated + quality scores

### Browse the wiki

The **Wiki** page shows the full directory tree. Click any page to read content and backlinks.

You can also open `backend/wiki-root/` directly in [Obsidian](https://obsidian.md/) for graph view and advanced navigation.

### Search & Q&A

The **Search** page offers two modes:
- **Quick search** — instant hybrid BM25 + vector results
- **AI Q&A** — RAG answer from the knowledge base; archive the answer as a new wiki page

### Lint

The **Lint** page scans the wiki for broken links, orphan pages, and format errors.

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/       # Routes: ingest / wiki / search / lint
│   │   ├── ingest/    # Document processing pipeline
│   │   ├── llm/       # LLM provider abstraction (MiniMax / Ollama / Claude)
│   │   ├── search/    # Hybrid search (BM25 + vector embeddings)
│   │   ├── eval/      # Import quality evaluation
│   │   ├── wiki/      # Wiki read/write, backlinks, lint
│   │   └── models/    # SQLite models
│   ├── wiki-root/     # Markdown knowledge base (user data, git-ignored)
│   ├── data/          # SQLite DB + search index
│   ├── config.example.yaml
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/     # IngestPage / WikiPage / SearchPage / LintPage
│       └── components/
├── deploy/
│   └── Caddyfile      # Caddy reverse proxy config
├── docker-compose.yml
└── .env.example
```

---

## Roadmap

- [ ] Token usage tracking and cost display
- [ ] Large document section splitting (H1-level sub-documents + parent-child relations)
- [ ] Semantic tag deduplication (synonym merging)
- [ ] Mobile responsive layout
- [ ] Batch import

---

## Contributing

Issues and PRs are welcome.

1. Fork the repo
2. Create a branch: `git checkout -b feat/your-feature`
3. Commit: `git commit -m 'feat: add some feature'`
4. Push: `git push origin feat/your-feature`
5. Open a Pull Request

---

## License

[MIT](LICENSE)

---

## 中文

[English](#wikiforge) | **中文**

> AI 驱动的文档知识编译器。上传 PDF、DOCX、PPTX，自动提炼为 sources / concepts / entities / topics 四层结构化 Wiki，支持 BM25 + 向量混合搜索、AI 问答、导入质量评估，兼容 Obsidian，本地优先部署。灵感来自 Andrej Karpathy 的 LLM Wiki 构想。

### 功能特性

| 功能 | 说明 |
|------|------|
| **多格式文档导入** | 支持 PDF、DOCX、PPTX、Markdown、TXT |
| **结构化 Wiki 生成** | LLM 将文档编译为 sources / concepts / entities / topics 四层知识结构 |
| **混合搜索** | BM25 全文检索（SQLite FTS5）+ 向量语义搜索并行执行 |
| **AI 问答** | 基于知识库的 RAG 问答，可将答案归档为新 Wiki 页面 |
| **导入质量评估** | 本地模型评估忠实度与完整度，防止 LLM 幻觉 |
| **Wiki Lint** | 检测悬空链接、孤立页面、格式问题 |
| **Obsidian 兼容** | Wiki 文件为标准 Markdown + Wikilink，直接用 Obsidian 打开 |
| **反向链接** | 每个页面显示所有引用它的页面 |
| **导入去重** | 内容哈希检测重复文档 |

### 前置要求

| 依赖 | 说明 |
|------|------|
| **MiniMax API Key** | 主力 LLM，[申请地址](https://platform.minimaxi.com/) |
| **Python 3.11+** | 后端运行环境 |
| **Node.js 18+** | 前端构建 |
| **Anthropic API Key** | 可选，图片型 PDF 的 Vision 处理 |
| **Ollama** | 可选，本地模型质量评估（`qwen3.5:9b`） |
| **Docker + Compose** | 可选，推荐一键部署方式 |

> 仅需 MiniMax Key 即可完整使用，Vision 和本地评估为可选项。

### 快速部署（Docker）

```bash
# 1. 克隆
git clone https://github.com/stardust-mem/WikiForge.git
cd wikiforge

# 2. 配置 API Keys
cp .env.example .env
# 编辑 .env，填入 MINIMAX_API_KEY

# 3. 配置 LLM
cp backend/config.example.yaml backend/config.yaml
# 按需编辑 config.yaml

# 4. 启动
docker compose up -d
```

访问 [http://localhost](http://localhost)

> 首次启动会下载 embedding 模型并安装依赖，需要几分钟。

### 本地开发

```bash
# 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml   # 填入 API keys
uvicorn app.main:app --reload --port 8000

# 前端（新终端）
cd frontend
npm install && npm run dev
```

### LLM 配置

`config.yaml` 支持灵活配置多个提供商，详细说明见[英文文档](#llm-configuration)。

**最简配置（仅 MiniMax）：**

```yaml
llm:
  cloud_provider: "minimax"
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: "your_key"
  local_provider: "minimax"
  local_model: "MiniMax-M2.7"
  local_api_key: "your_key"
```

也支持 DeepSeek、Kimi、OpenAI 兼容接口，以及 Ollama 本地模型。

### 使用方法

1. **导入** — 上传文档，LLM 自动生成结构化 Wiki 页面
2. **Wiki** — 浏览知识库目录树，或用 Obsidian 直接打开 `backend/wiki-root/`
3. **搜索问答** — 快速搜索（混合检索）或 AI 问答（RAG）
4. **健康检查** — 检测 Wiki 中的悬空链接和格式问题

### 路线图

- [ ] Token 用量追踪与成本展示
- [ ] 大型文档章节拆分
- [ ] 标签语义去重
- [ ] 移动端响应式布局
- [ ] 批量导入支持

### 贡献

欢迎提交 Issue 和 Pull Request，贡献流程见[英文文档](#contributing)。

### 许可证

[MIT](LICENSE)
