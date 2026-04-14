# NEWTYPE — AI 驱动的个人知识管理系统

> 灵感来源于 Andrej Karpathy 的 LLM Wiki 构想 —— 将你的文档编译成结构化的、可查询的知识库。

NEWTYPE 是一个本地优先的 PKM（Personal Knowledge Management）系统。你上传文档，它自动通过 LLM 将内容"编译"成分层的 Wiki 知识库：概念页、实体页、主题聚合页相互交叉引用，并支持混合语义搜索和 AI 问答。

Wiki 以 Markdown 文件形式存储在本地，天然兼容 [Obsidian](https://obsidian.md/)。

---

## 功能特性

| 功能 | 说明 |
|------|------|
| **多格式文档导入** | 支持 PDF、DOCX、PPTX、Markdown、TXT |
| **LLM 自动 Wiki 生成** | 文档按 sources / concepts / entities / topics 四层结构化提炼 |
| **混合搜索** | BM25 全文检索（SQLite FTS5）+ 向量语义搜索并行执行 |
| **AI 问答** | 基于 Wiki 知识库的 RAG 问答，可归档答案为新 Wiki 页面 |
| **导入质量评估** | 本地模型评估"忠实度"与"完整度"，防止 LLM 幻觉 |
| **Wiki Lint** | 检测悬空链接、缺失交叉引用、格式问题 |
| **Obsidian 兼容** | Wiki 文件为标准 Markdown + Wikilink 格式，直接用 Obsidian 打开 |
| **反向链接** | 每个页面显示所有引用它的页面 |
| **导入去重** | 内容哈希检测重复文档，防止重复处理 |

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端 (React + Vite)                      │
│   IngestPage · WikiPage · SearchPage · LintPage                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ REST API
┌───────────────────────────▼─────────────────────────────────────┐
│                      后端 (FastAPI)                               │
│  /api/ingest  /api/wiki  /api/search  /api/lint                  │
│                                                                  │
│  ┌──────────────┐  ┌─────────────┐  ┌──────────────────────┐   │
│  │ Ingest 管道  │  │ 混合搜索     │  │   LLM 路由层          │   │
│  │ PDF·DOCX·PPT │  │ BM25 + Vec  │  │  cloud/local/vision  │   │
│  └──────────────┘  └─────────────┘  └──────────────────────┘   │
│                                                                  │
│  SQLite (wiki.db)        wiki-root/ (Markdown 文件)              │
└─────────────────────────────────────────────────────────────────┘
```

**wiki-root 四层知识结构：**

```
wiki-root/
├── CLAUDE.md          # Wiki Schema 定义（LLM 指导文件）
├── index.md           # 自动维护的内容目录
├── log.md             # 操作日志
├── sources/           # 每份原始文档的详细摘要页
├── entities/          # 具名实体页（产品、组织、人物）
├── concepts/          # 概念页（技术方法、抽象知识）
└── topics/            # 主题聚合页（跨文档的知识汇总）
```

---

## 前置要求

| 依赖 | 说明 |
|------|------|
| **Python 3.11+** | 后端运行环境 |
| **Node.js 18+** | 前端构建 |
| **MiniMax API Key** | 主力 LLM（[申请地址](https://platform.minimaxi.com/)） |
| **Anthropic API Key** | 可选，用于图片型 PDF 的 Vision 处理 |
| **Ollama** | 可选，用于本地模型评估质量（`qwen3.5:9b` 等） |
| **Docker + Docker Compose** | 可选，一键部署推荐方式 |

> **仅有 MiniMax Key 也能正常使用**，Vision 和本地评估为可选功能。

---

## 快速部署（Docker Compose 推荐）

### 1. 克隆仓库

```bash
git clone https://github.com/your-org/newtype-wiki.git
cd newtype-wiki
```

### 2. 配置 API Keys

```bash
cp .env.example .env
```

编辑 `.env`：

```env
MINIMAX_API_KEY=your_minimax_key_here

# 可选：图片型 PDF 处理（Claude Vision）
ANTHROPIC_API_KEY=your_anthropic_key_here

# 可选：Cloudflare Tunnel 外网访问
CLOUDFLARE_TUNNEL_TOKEN=
```

### 3. 配置 LLM

```bash
cp backend/config.example.yaml backend/config.yaml
```

默认配置使用 MiniMax，如需修改模型或接入其他 LLM 提供商，编辑 `backend/config.yaml`。

### 4. 启动服务

```bash
docker compose up -d
```

访问 [http://localhost](http://localhost)

> **首次启动**会拉取镜像并安装依赖（包括 `sentence-transformers` embedding 模型），需要几分钟。

### 可选：外网访问（Cloudflare Tunnel）

在 `.env` 中填入 `CLOUDFLARE_TUNNEL_TOKEN` 后：

```bash
docker compose --profile tunnel up -d
```

---

## 本地开发部署

不依赖 Docker，适合开发调试。

### 后端

```bash
cd backend

# 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置（参考上方 Docker 部署步骤 2-3）
cp config.example.yaml config.yaml
# 编辑 config.yaml 填入 API keys

# 启动
uvicorn app.main:app --reload --port 8000
```

后端运行在 `http://localhost:8000`，API 文档在 `http://localhost:8000/docs`。

### 前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端运行在 `http://localhost:5173`。

> 前端开发模式下，API 请求会通过 Vite proxy 转发到 `:8000`（已在 `vite.config.ts` 中配置）。

---

## LLM 配置详解

`backend/config.yaml` 支持灵活配置多个 LLM 提供商：

```yaml
llm:
  # 云端模型：用于 Wiki 生成、语义分段、AI 问答（复杂任务）
  cloud_provider: "minimax"       # minimax / claude / deepseek / kimi / openai
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: ""               # 或通过 MINIMAX_API_KEY 环境变量设置

  # 本地模型：用于分类、简单摘要（轻量任务）
  # 没有 Ollama 时，可将 local_* 设置与 cloud_* 相同，全部走云端
  local_provider: "minimax"
  local_model: "MiniMax-M2.7"
  local_api_key: ""

  # Vision 模型：用于图片型 PDF（需要多模态能力）
  vision_provider: "claude"
  vision_model: "claude-sonnet-4-6"
  vision_api_key: ""              # 或通过 ANTHROPIC_API_KEY 环境变量设置

  # 向量嵌入模型（本地运行，首次启动自动下载）
  embedding_model: "BAAI/bge-small-zh-v1.5"
```

### 只用 MiniMax（最简配置）

```yaml
llm:
  cloud_provider: "minimax"
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: "your_key"
  local_provider: "minimax"
  local_model: "MiniMax-M2.7"
  local_api_key: "your_key"
  vision_provider: ""
  vision_model: ""
  vision_api_key: ""
```

### 接入 DeepSeek / Kimi / OpenAI 兼容接口

```yaml
llm:
  cloud_provider: "deepseek"
  cloud_model: "deepseek-chat"
  cloud_api_key: "your_key"
  cloud_base_url: "https://api.deepseek.com/v1"
```

### 使用 Ollama 本地模型（eval 质量评估）

先拉取模型：
```bash
ollama pull qwen3.5:9b
```

配置 `config.yaml`：
```yaml
llm:
  local_provider: "ollama"
  local_model: "qwen3.5:9b"
  local_base_url: "http://localhost:11434/v1"
  local_api_key: "ollama"
```

---

## 使用方法

### 1. 导入文档

打开 `http://localhost` → **导入** 页面，上传文档（PDF / DOCX / PPTX / MD / TXT）。

系统将：
1. 提取文档内容（支持图片型 PDF 的 Vision 识别）
2. LLM 分析并生成 sources / concepts / entities / topics 页面
3. 更新 index.md 和搜索索引
4. 展示导入报告（创建/更新页面数、质量评分）

### 2. 浏览 Wiki

**Wiki** 页面展示知识库目录树，点击任意页面查看内容及反向链接。

也可直接用 Obsidian 打开 `backend/wiki-root/` 目录，享受完整的知识图谱体验。

### 3. 搜索与问答

**搜索** 页面提供两种模式：
- **快速搜索**：BM25 + 向量混合检索，即时返回相关页面
- **AI 问答**：基于知识库的 RAG 问答，可将回答归档为新 Wiki 页面

### 4. Wiki 检查

**Lint** 页面检测知识库中的问题：悬空链接、孤立页面、格式错误等。

---

## 项目结构

```
.
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI 路由（ingest / wiki / search / lint）
│   │   ├── ingest/        # 文档处理管道（PDF/DOCX/PPTX/MD 提取）
│   │   ├── llm/           # LLM 提供商抽象层（MiniMax / Ollama / Claude）
│   │   ├── search/        # 混合搜索（BM25 + 向量嵌入）
│   │   ├── eval/          # 导入质量评估（忠实度 + 完整度）
│   │   ├── wiki/          # Wiki 管理（读写、反向链接、lint）
│   │   ├── models/        # 数据库模型（SQLite）
│   │   └── config.py      # 配置加载
│   ├── wiki-root/         # Markdown 知识库（用户数据，不纳入版本控制）
│   ├── data/              # SQLite 数据库 + 搜索索引
│   ├── config.example.yaml
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/         # IngestPage / WikiPage / SearchPage / LintPage
│   │   └── components/    # 共享组件
│   ├── package.json
│   └── Dockerfile
├── deploy/
│   └── Caddyfile          # Caddy 反向代理配置
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## 路线图

- [ ] Token 用量追踪与成本展示
- [ ] 大型文档章节拆分（H1 级子文档 + 父子关系）
- [ ] 标签语义去重（同义标签合并）
- [ ] 移动端响应式布局
- [ ] 操作日志 Git 自动提交
- [ ] 批量导入支持

---

## 贡献

欢迎提交 Issue 和 Pull Request。

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feat/your-feature`
3. 提交变更：`git commit -m 'feat: add some feature'`
4. Push 分支：`git push origin feat/your-feature`
5. 提交 Pull Request

---

## License

MIT License — 详见 [LICENSE](LICENSE) 文件。
