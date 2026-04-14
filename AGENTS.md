# AGENTS.md — WikiForge Deployment & Development Guide for AI Agents

This file is the authoritative reference for AI agents (Claude Code, Cursor, Copilot, etc.) working on this repository. Read this before writing any code or running any commands.

---

## Project Overview

WikiForge is an AI-powered document-to-wiki compiler. Users upload documents (PDF, DOCX, PPTX, Markdown, TXT); the backend LLM pipeline compiles them into a structured Markdown knowledge base (wiki-root/) organized into four layers: `sources/`, `concepts/`, `entities/`, `topics/`. The frontend provides document import, wiki browsing, hybrid search, and AI Q&A.

**Tech stack:**
- Backend: Python 3.11+, FastAPI, SQLite (aiosqlite), sentence-transformers, BM25s
- Frontend: React 18, TypeScript, Vite, Ant Design
- LLM: OpenAI-compatible SDK (MiniMax tested; DeepSeek/Kimi/Ollama untested)
- Deployment: Docker Compose, Caddy reverse proxy

---

## Repository Layout

```
WikiForge/
├── AGENTS.md                  # This file
├── README.md                  # User-facing documentation
├── docker-compose.yml         # Production/dev Docker orchestration
├── .env.example               # Environment variable template
│
├── backend/
│   ├── pyproject.toml         # Python dependencies (pip install -e .)
│   ├── Dockerfile
│   ├── config.example.yaml    # LLM + path config template → copy to config.yaml
│   ├── config.yaml            # ← GITIGNORED, must be created by user
│   ├── app/
│   │   ├── main.py            # FastAPI entrypoint, router registration
│   │   ├── config.py          # Config loader (YAML + env var override)
│   │   ├── api/               # Route handlers: ingest, wiki, search, lint
│   │   ├── ingest/            # Document processing pipeline
│   │   │   ├── pipeline.py    # Main ingest orchestration (calls LLM)
│   │   │   ├── extractors/    # PDF / DOCX / PPTX / Markdown text extraction
│   │   │   ├── segmenter.py   # LLM-based semantic segmentation
│   │   │   ├── classifier.py  # Page type classification (source/concept/entity/topic)
│   │   │   └── tasks.py       # In-memory async task tracker
│   │   ├── llm/
│   │   │   ├── router.py      # Task → provider mapping (cloud/local/vision/eval)
│   │   │   ├── openai_compat.py  # OpenAI SDK wrapper (MiniMax/DeepSeek/Kimi/Ollama)
│   │   │   ├── claude.py      # Anthropic SDK wrapper (vision only)
│   │   │   └── prompts.py     # All LLM prompt templates
│   │   ├── search/
│   │   │   ├── hybrid.py      # BM25 + vector search, parallel execution
│   │   │   ├── bm25_index.py  # SQLite FTS5 BM25 index
│   │   │   ├── embeddings.py  # sentence-transformers vector embeddings
│   │   │   └── query.py       # RAG Q&A pipeline
│   │   ├── wiki/
│   │   │   ├── generator.py   # LLM wiki page writer
│   │   │   ├── refs.py        # Backlink computation
│   │   │   ├── index.py       # index.md auto-maintenance
│   │   │   └── git_ops.py     # Optional git auto-commit
│   │   ├── eval/
│   │   │   └── evaluator.py   # Import quality scoring (faithfulness + completeness)
│   │   ├── lint/
│   │   │   └── checker.py     # Broken link / orphan page detection
│   │   └── models/
│   │       ├── database.py    # SQLite schema + async connection helpers
│   │       └── schemas.py     # Pydantic request/response models
│   ├── wiki-root/             # Markdown knowledge base (gitignored content)
│   │   ├── CLAUDE.md          # Wiki schema definition (LLM reads this)
│   │   ├── index.md           # Auto-maintained directory (gitignored)
│   │   ├── log.md             # Operation log (gitignored)
│   │   ├── sources/           # Per-document summary pages (gitignored)
│   │   ├── entities/          # Named entity pages (gitignored)
│   │   ├── concepts/          # Concept pages (gitignored)
│   │   └── topics/            # Topic aggregation pages (gitignored)
│   └── data/
│       ├── wiki.db            # SQLite database (gitignored)
│       ├── uploads/           # Uploaded documents (gitignored)
│       └── bm25_index/        # BM25 search index (gitignored)
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts         # Dev server on :5173, proxies /api → :8000
│   ├── Dockerfile
│   └── src/
│       ├── App.tsx            # Router setup
│       ├── components/
│       │   └── Layout.tsx     # Nav bar + page layout
│       └── pages/
│           ├── IngestPage.tsx # Document upload + task progress
│           ├── WikiPage.tsx   # Wiki directory tree + page viewer
│           ├── SearchPage.tsx # Quick search + AI Q&A tabs
│           └── LintPage.tsx   # Wiki health check
│
├── deploy/
│   └── Caddyfile              # Caddy reverse proxy (:80 → api:8000 / web:5173)
│
└── scripts/
    └── deploy.sh              # One-shot local build + restart script
```

---

## Prerequisites

| Requirement | Version | Check |
|-------------|---------|-------|
| Python | 3.11+ | `python3 --version` |
| Node.js | 18+ | `node --version` |
| pip | any | `pip --version` |
| Docker + Compose | any | `docker compose version` |
| MiniMax API key | — | Required (https://platform.minimaxi.com/) |

---

## Configuration

### Step 1 — Create config.yaml

```bash
cp backend/config.example.yaml backend/config.yaml
```

Minimum required fields:

```yaml
llm:
  cloud_provider: "minimax"
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: "YOUR_MINIMAX_KEY"   # or leave blank and set env var

  local_provider: "minimax"
  local_model: "MiniMax-M2.7"
  local_api_key: "YOUR_MINIMAX_KEY"

  vision_provider: ""    # leave blank to skip Vision (image PDFs will be skipped)
  vision_api_key: ""

  embedding_model: "BAAI/bge-small-zh-v1.5"  # auto-downloaded on first run
```

### Step 2 — Create .env (Docker only)

```bash
cp .env.example .env
# Set MINIMAX_API_KEY in .env
```

### Environment variable override

`config.py` reads env vars after loading YAML. Env vars take precedence:
- `MINIMAX_API_KEY` → overwrites `cloud_api_key` and `local_api_key`
- `ANTHROPIC_API_KEY` → overwrites `vision_api_key`
- `OPENAI_API_KEY` → fallback for `cloud_api_key` if blank

---

## Local Development Setup

Run backend and frontend in separate terminals.

### Backend

```bash
cd backend

# Create virtualenv
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# Install dependencies
pip install -e "."

# Configure (see above)
cp config.example.yaml config.yaml
# edit config.yaml — fill in cloud_api_key and local_api_key

# Start
uvicorn app.main:app --reload --port 8000
```

Expected output:
```
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Expected output:
```
VITE v5.x  ready in Xms
➜  Local:   http://localhost:5173/
```

Frontend at http://localhost:5173 — API calls auto-proxied to :8000.

---

## Docker Deployment

```bash
# 1. Configure
cp .env.example .env         # fill MINIMAX_API_KEY
cp backend/config.example.yaml backend/config.yaml   # fill api keys

# 2. Start
docker compose up -d

# 3. Verify
curl http://localhost/api/health
# Expected: {"status":"ok","cloud_provider":"minimax","local_provider":"minimax"}
```

Services:
| Service | Container port | Role |
|---------|---------------|------|
| caddy | 80, 443 | Reverse proxy |
| api | 8000 (internal) | FastAPI backend |
| web | 5173 (internal) | Vite dev server |
| tunnel | — | Cloudflare Tunnel (optional, `--profile tunnel`) |

Logs:
```bash
docker compose logs -f api     # backend logs
docker compose logs -f web     # frontend logs
```

---

## Verification Checklist

After starting (Docker or local), verify in order:

```bash
# 1. Backend health
curl http://localhost:8000/api/health

# 2. Wiki root initialized
curl http://localhost:8000/api/wiki/pages
# Expected: [] (empty array on first run)

# 3. Search endpoint
curl -X POST http://localhost:8000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "test", "top_k": 5}'
# Expected: [] (empty results)

# 4. Upload a test document (requires a PDF/DOCX file)
curl -X POST http://localhost:8000/api/ingest \
  -F "file=@/path/to/test.pdf"
# Expected: {"task_id": "...", "status": "pending"}
```

---

## Key Architecture Notes

### LLM Task Routing

`app/llm/router.py` maps task names to provider types:

```python
TASK_ROUTING = {
    "classify":     "local",    # lightweight — uses local_provider
    "summarize":    "local",
    "segment":      "cloud",    # complex — uses cloud_provider
    "wiki_generate":"cloud",
    "vision":       "vision",   # image PDF OCR — uses vision_provider
    "query":        "cloud",    # Q&A RAG — uses cloud_provider
    "eval":         "eval",     # quality scoring — uses eval_provider (Ollama)
}
```

If `local_provider` == `cloud_provider` (same API key), all tasks go to the cloud. This is the recommended minimal setup.

### Database Schema

SQLite at `backend/data/wiki.db`. Tables:
- `sources` — uploaded document metadata (id, filename, content_hash)
- `wiki_pages` — wiki page metadata (page_id, title, category, topic_tags)
- `source_page_map` — many-to-many: which pages came from which source
- `page_refs` — wikilink graph (from_page_id → to_page_id)
- `wiki_fts` — FTS5 virtual table for BM25 search
- `page_embeddings` — vector embeddings (sqlite-vec)

### Ingest Pipeline Flow

```
Upload file
    → extractors/ (text extraction by file type)
    → segmenter.py (LLM splits into logical sections)
    → classifier.py (LLM assigns source/concept/entity/topic)
    → generator.py (LLM writes Markdown wiki pages)
    → wiki-root/{category}/{slug}.md (written to disk)
    → database.py (metadata + FTS + vectors indexed)
    → index.md updated
    → evaluator.py (optional quality scoring via eval_provider)
```

### Wiki Content is Gitignored

`wiki-root/concepts/`, `entities/`, `sources/`, `topics/`, `index.md`, `log.md` are all gitignored — this is intentional. Each user's knowledge base is personal. Only `wiki-root/CLAUDE.md` (the schema) and `.gitkeep` placeholders are tracked.

---

## Common Issues

**Backend fails to start — `ModuleNotFoundError`**
```bash
# Ensure virtualenv is activated
source .venv/bin/activate
pip install -e "."
```

**`config.yaml not found` warning on startup**
The app runs with defaults (no LLM calls will work). Create `config.yaml` from the example.

**LLM call fails with 401 / authentication error**
- Check `cloud_api_key` in `config.yaml`
- Env var `MINIMAX_API_KEY` overrides YAML — make sure it's set correctly

**Embedding model download hangs**
First run downloads `BAAI/bge-small-zh-v1.5` (~100MB) from HuggingFace. Set mirror if needed:
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

**Docker: `api` container exits immediately**
```bash
docker compose logs api
# Usually a missing config.yaml or bad API key
```

**`wiki.db` locked error**
Multiple processes accessing the DB. Kill all backend processes and restart.

---

## Adding a New LLM Provider

1. If the provider has an OpenAI-compatible API — just set `cloud_base_url` in `config.yaml`. No code changes needed.
2. If it requires a custom SDK (like Anthropic) — add a new class in `app/llm/` extending `LLMProvider` (see `claude.py` as reference), then register it in `router.py` `_build_provider()`.

---

## Running Tests

```bash
cd backend
source .venv/bin/activate
pytest tests/ -v
```

Tests are minimal — integration tests require a running backend with valid API keys.
