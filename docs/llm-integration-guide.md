# LLM 多模型接入指南

> 基于 WikiForge 项目实战经验总结。适用于需要同时接入云端模型和本地模型的 Python 后端项目。

## 架构总览

```
┌─────────────────────────────────────────────────────┐
│                    业务层                             │
│  classify / segment / generate / eval / vision       │
└───────────────────┬─────────────────────────────────┘
                    │ get_provider(task)
┌───────────────────▼─────────────────────────────────┐
│                  路由层 (router.py)                    │
│  TASK_ROUTING: task → provider_type                   │
│  缓存: provider_type → LLMProvider 单例               │
└───┬──────────┬──────────┬──────────┬────────────────┘
    │          │          │          │
┌───▼───┐ ┌───▼───┐ ┌───▼───┐ ┌───▼───┐
│ cloud │ │ local │ │ eval  │ │vision │
│MiniMax│ │MiniMax│ │Ollama │ │Claude │
│DeepSk │ │Ollama │ │(本地) │ │(多模态)│
│OpenAI │ │  ...  │ │       │ │       │
└───┬───┘ └───┬───┘ └───┬───┘ └───┬───┘
    │         │         │         │
┌───▼─────────▼─────────▼───┐ ┌───▼───┐
│   OpenAICompatProvider    │ │Claude │
│   (统一 OpenAI 兼容接口)   │ │Provider│
└───────────────────────────┘ └───────┘
```

**核心设计原则：**
- 一个抽象接口 `LLMProvider`，两个实现（OpenAI 兼容 + Claude 原生）
- 任务级路由：不同任务走不同模型，按需分配算力和成本
- 配置驱动：切换模型只改 config.yaml，不改代码

---

## 快速开始

### 1. 依赖安装

```bash
pip install openai anthropic
# 本地模型需要 Ollama
brew install ollama  # macOS
```

### 2. 最小配置 (config.yaml)

```yaml
llm:
  # 云端模型 — 复杂任务（生成、问答）
  cloud_provider: "minimax"
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: "your-api-key"
  cloud_base_url: "https://api.minimaxi.com/v1"

  # 本地模型 — 轻量任务（分类、摘要）
  local_provider: "ollama"
  local_model: "qwen2.5:14b"
  local_api_key: "ollama"
  local_base_url: "http://localhost:11434"
```

### 3. 调用方式

```python
from app.llm.router import get_provider

# 根据任务自动选择模型
provider = get_provider("classify")   # → 走 local
provider = get_provider("wiki_generate")  # → 走 cloud

# 普通对话
text = await provider.chat(messages=[
    {"role": "system", "content": "你是助手"},
    {"role": "user", "content": "你好"},
])

# JSON 结构化输出
result = await provider.chat_json(messages=[...])
# 返回 dict，自动处理 markdown 代码块、<think> 标签等干扰
```

---

## 核心组件详解

### Provider 抽象层 (base.py)

```python
class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages, temperature=0.3, max_tokens=4096) -> str:
        """普通对话，返回文本"""

    @abstractmethod
    async def chat_json(self, messages, temperature=0.1, max_tokens=4096) -> dict:
        """结构化输出，返回解析后的 JSON dict"""

    async def vision(self, image_bytes, prompt, media_type="image/png") -> str:
        """图片理解（可选，子类按需实现）"""
```

**设计要点：**
- 只定义 3 个方法，保持接口极简
- `chat_json` 是最常用的方法 — 业务逻辑几乎都需要结构化输出
- `vision` 给默认 `NotImplementedError`，不是所有模型都需要多模态

### OpenAI 兼容 Provider (openai_compat.py)

一个实现覆盖 90% 的模型：MiniMax、DeepSeek、Kimi、Ollama、OpenAI。

```python
class OpenAICompatProvider(LLMProvider):
    def __init__(self, base_url: str, api_key: str, model: str):
        self.client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=300.0,  # 推理模型响应慢，5分钟超时
        )
        self.model = model
```

**关键处理逻辑：**

#### 1. `<think>` 推理块剥离

MiniMax M2.x、Qwen3、DeepSeek-R1 等模型会在输出中嵌入推理过程：

```
<think>用户要求JSON输出，我需要分析...</think>
{"result": "actual output"}
```

必须在返回前剥离：

```python
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

def _strip_reasoning(text: str) -> str:
    return _THINK_BLOCK_RE.sub("", text).strip()
```

#### 2. JSON 输出清理

LLM 经常在 JSON 外面包裹 markdown 代码块：

````
```json
{"key": "value"}
```
````

清理逻辑：

```python
def _clean_json_text(text: str) -> str:
    text = _strip_reasoning(text)       # 先剥离 <think> 块
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)  # 去掉开头 ```json
    text = re.sub(r"\s*```$", "", text)            # 去掉结尾 ```
    return text
```

#### 3. JSON 解析容错

即使清理后仍可能有前缀/后缀文字，兜底提取第一个 `{...}` 块：

```python
try:
    return json.loads(text, strict=False)
except json.JSONDecodeError:
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start:end + 1], strict=False)
    raise LLMOutputError(f"LLM did not return valid JSON: {text[:200]}")
```

> **`strict=False` 很重要** — LLM 输出的 JSON 经常包含不合规的控制字符。

#### 4. 重试机制

```python
MAX_RETRIES = 3
RETRY_DELAY = 2  # 指数退避：2s, 4s, 6s

async def _call_with_retry(self, messages, temperature, max_tokens):
    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            return await self.client.chat.completions.create(...)
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY * (attempt + 1)
                await asyncio.sleep(delay)
    raise last_err
```

### Claude Provider (claude.py)

Anthropic Claude 使用原生 SDK（消息格式不同于 OpenAI）：

```python
class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)

    def _convert_messages(self, messages):
        """OpenAI 格式 → Anthropic 格式（system 消息需要单独传）"""
        system = ""
        converted = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                converted.append({"role": msg["role"], "content": msg["content"]})
        return system, converted
```

**何时用 Claude：**
- Vision 任务（图片理解），Claude 的多模态能力最强
- 需要极高质量的复杂推理（但成本高）
- 业务层代码不感知 provider 差异，统一走 `get_provider(task)`

### 路由层 (router.py)

```python
# 任务 → provider 类型映射
TASK_ROUTING = {
    "classify":      "local",   # 轻量，本地够用
    "summarize":     "local",   # 轻量
    "segment":       "cloud",   # 需要理解语义边界
    "wiki_generate": "cloud",   # 最复杂的任务
    "query":         "cloud",   # RAG 问答
    "eval":          "eval",    # 质量评估，走本地 Ollama
    "vision":        "vision",  # 图片理解，走 Claude
}
```

**路由设计原则：**

| 原则 | 说明 |
|------|------|
| **成本分层** | 简单任务走本地/便宜模型，复杂任务走强模型 |
| **独立缓存** | 每个 provider_type 一个单例，避免重复创建客户端 |
| **配置可选** | 没有 Ollama？把 local 配成和 cloud 一样即可 |
| **按需扩展** | 新增任务类型只需加一行映射 |

---

## 支持的模型供应商

### 云端模型

| 供应商 | base_url | 推荐模型 | 特点 |
|--------|----------|---------|------|
| **MiniMax** | `https://api.minimaxi.com/v1` | MiniMax-M2.7 | 中文强，205K 上下文，性价比高 |
| **DeepSeek** | `https://api.deepseek.com` | deepseek-chat | 推理强，价格便宜 |
| **Kimi (Moonshot)** | `https://api.moonshot.cn/v1` | moonshot-v1-128k | 超长上下文 |
| **OpenAI** | `https://api.openai.com/v1` | gpt-4o | 综合最强 |
| **Anthropic** | 原生 SDK | claude-sonnet-4-6 | Vision 最强，需用 ClaudeProvider |

### 本地模型 (Ollama)

| 模型 | 命令 | 大小 | 内存需求 | 适合任务 |
|------|------|------|---------|---------|
| **Qwen3.5 9B** | `ollama pull qwen3.5:9b` | 6GB | ~9GB | 中文 eval/分类/摘要（推荐） |
| **Qwen3 14B** | `ollama pull qwen3:14b` | 9GB | ~12GB | 复杂判断，带 thinking 模式 |
| **Qwen2.5 14B** | `ollama pull qwen2.5:14b` | 9GB | ~12GB | 稳定，社区验证充分 |
| **DeepSeek-R1 14B** | `ollama pull deepseek-r1:14b` | 9GB | ~12GB | 推理链透明 |
| **Gemma4 26B** | `ollama pull gemma4:26b` | 17GB | ~20GB | 综合能力强，需要较大内存 |

---

## 配置模板

### 完整配置示例 (config.yaml)

```yaml
llm:
  # ═══ 云端模型 ═══
  # 用于：wiki 生成、语义分段、RAG 问答
  cloud_provider: "minimax"          # minimax / deepseek / kimi / openai
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: "your-cloud-key"
  cloud_base_url: "https://api.minimaxi.com/v1"

  # ═══ 本地模型（轻量任务）═══
  # 用于：文档分类、摘要
  # 无 Ollama 时可配成和 cloud 相同
  local_provider: "minimax"          # ollama 或与 cloud 相同
  local_model: "MiniMax-M2.7"
  local_api_key: ""                  # 留空则 fallback 到 cloud_api_key
  local_base_url: "https://api.minimaxi.com/v1"

  # ═══ Eval 模型（质量评估）═══
  # 用于：导入后对比原文与生成内容的忠实度/完整度
  # 走本地 Ollama，零 API 成本
  eval_provider: "ollama"
  eval_model: "qwen3.5:9b"
  eval_api_key: "ollama"
  eval_base_url: "http://localhost:11434"

  # ═══ Vision 模型（图片理解）═══
  # 用于：PDF/PPTX 中的图表描述
  # 需要多模态能力，推荐 Claude
  vision_provider: "claude"
  vision_model: "claude-sonnet-4-6"
  vision_api_key: "your-anthropic-key"

  # ═══ 嵌入模型 ═══
  embedding_model: "BAAI/bge-small-zh-v1.5"
```

### 常见配置场景

#### 场景 1：全部走云端（最简单）

```yaml
llm:
  cloud_provider: "minimax"
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: "your-key"
  cloud_base_url: "https://api.minimaxi.com/v1"
  # local/eval 都 fallback 到 cloud
  local_provider: "minimax"
  local_model: "MiniMax-M2.7"
  eval_provider: "minimax"
  eval_model: "MiniMax-M2.7"
  eval_api_key: "your-key"
  eval_base_url: "https://api.minimaxi.com/v1"
```

#### 场景 2：云端 + 本地混合（推荐）

```yaml
llm:
  cloud_provider: "minimax"
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: "your-key"
  cloud_base_url: "https://api.minimaxi.com/v1"
  local_provider: "ollama"
  local_model: "qwen3.5:9b"
  local_base_url: "http://localhost:11434"
  eval_provider: "ollama"
  eval_model: "qwen3:14b"
  eval_base_url: "http://localhost:11434"
```

#### 场景 3：全部本地（离线/隐私优先）

```yaml
llm:
  cloud_provider: "ollama"
  cloud_model: "qwen3:14b"
  cloud_api_key: "ollama"
  cloud_base_url: "http://localhost:11434"
  local_provider: "ollama"
  local_model: "qwen3.5:9b"
  local_base_url: "http://localhost:11434"
  eval_provider: "ollama"
  eval_model: "qwen3.5:9b"
  eval_base_url: "http://localhost:11434"
```

---

## Ollama 本地部署指南

### 安装

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# 启动服务（后台常驻）
ollama serve
```

### 模型管理

```bash
# 拉取模型
ollama pull qwen3.5:9b
ollama pull qwen3:14b

# 列出已安装模型
ollama list

# 删除模型
ollama rm qwen2.5:14b

# 测试模型
ollama run qwen3.5:9b "你好，请用JSON格式回答：{\"status\": \"ok\"}"
```

### 验证 API 可用

```bash
# Ollama 暴露 OpenAI 兼容接口
curl http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen3.5:9b",
    "messages": [{"role": "user", "content": "ping"}],
    "max_tokens": 10
  }'
```

### 硬件参考

| 内存 | 推荐模型 | 备注 |
|------|---------|------|
| 8GB | qwen3:8b (Q4) | 勉强可用，留给系统的余量少 |
| 16GB | qwen3.5:9b / qwen3:14b (Q4) | 舒适运行 14B |
| 32GB | qwen3:14b + 后端服务同时跑 | 推荐配置 |
| 64GB+ | qwen3:32b 或 gemma4:26b | 可以跑更大模型 |

---

## 新增任务类型指南

当项目需要新增一种 LLM 任务时，按以下步骤操作：

### Step 1: 定义 Prompt

```python
# prompts.py
NEW_TASK_SYSTEM = """你是xxx专家。输出严格 JSON 格式：
{
  "field1": "...",
  "field2": 0
}"""

NEW_TASK_USER = """处理以下内容：{content}"""
```

### Step 2: 添加路由

```python
# router.py
TASK_ROUTING = {
    ...
    "new_task": "local",  # 或 "cloud" / "eval" / 自定义类型
}
```

如果需要独立的 provider 配置（不共享已有的 cloud/local）：

```python
# config.py — LLMConfig 中添加
new_task_provider: str = "ollama"
new_task_model: str = "qwen3.5:9b"
new_task_api_key: str = "ollama"
new_task_base_url: str = "http://localhost:11434"

# router.py — get_provider 中添加
elif provider_type == "new_task":
    _providers[cache_key] = _build_provider(
        "new_task", cfg.new_task_provider,
        api_key=cfg.new_task_api_key,
        base_url=cfg.new_task_base_url,
        model=cfg.new_task_model,
    )
```

### Step 3: 业务调用

```python
async def do_new_task(content: str) -> dict:
    provider = get_provider("new_task")
    result = await provider.chat_json(
        messages=[
            {"role": "system", "content": NEW_TASK_SYSTEM},
            {"role": "user", "content": NEW_TASK_USER.format(content=content)},
        ],
        max_tokens=2048,
    )
    return result
```

---

## 踩坑记录

### 1. Ollama base_url 需要加 `/v1`

Ollama 原生 API 地址是 `http://localhost:11434`，但 OpenAI SDK 需要 `/v1` 后缀。Router 中已自动处理：

```python
if provider_name == "ollama" and not base_url.endswith("/v1"):
    base_url = base_url.rstrip("/") + "/v1"
```

config.yaml 中写不写 `/v1` 都行。

### 2. JSON 输出不稳定的应对

不同模型的 JSON 输出稳定性差异大：

| 模型 | JSON 稳定性 | 常见问题 |
|------|------------|---------|
| Qwen3/3.5 | ⭐⭐⭐⭐⭐ | 最稳定 |
| MiniMax M2.7 | ⭐⭐⭐⭐ | 偶尔带 `<think>` 块 |
| DeepSeek | ⭐⭐⭐ | 推理链长，JSON 可能被推理文本包裹 |
| Llama 3.3 | ⭐⭐⭐ | 偶尔输出 markdown 代码块 |

**最佳实践：**
- system prompt 末尾加 `你必须以 JSON 格式输出，不要包含 markdown 代码块标记。不要输出任何思考过程。`
- `_clean_json_text()` 统一清理
- `json.loads(text, strict=False)` 容忍控制字符
- 兜底提取 `{...}` 块

### 3. 超时设置

推理模型（特别是带 thinking 的）响应很慢，默认超时要设够：

```python
self.client = AsyncOpenAI(
    timeout=300.0,  # 5 分钟，不能太短
)
```

本地 Ollama 首次推理需要加载模型到内存（冷启动），可能需要 30-60 秒。

### 4. 本地模型内存管理

Ollama 默认会在 GPU 内存中保持模型加载（热启动快），但会长期占用内存。如果需要释放：

```bash
# 卸载所有模型释放内存
curl http://localhost:11434/api/generate -d '{"model": "qwen3.5:9b", "keep_alive": 0}'
```

### 5. 环境变量覆盖

支持通过环境变量覆盖 config.yaml 中的 API key（优先级更高），避免密钥硬编码：

```bash
export MINIMAX_API_KEY="sk-xxx"        # → cloud_api_key + local_api_key
export ANTHROPIC_API_KEY="sk-ant-xxx"  # → vision_api_key
export OPENAI_API_KEY="sk-xxx"         # → cloud_api_key fallback
```

### 6. 中文模型选型经验

| 需求 | 推荐 | 原因 |
|------|------|------|
| 中文文档理解 | Qwen 系列 | 阿里专为中文优化 |
| 代码生成 | Qwen2.5-Coder / DeepSeek | 代码特化训练 |
| 图片理解 | Claude Sonnet | 多模态最强 |
| 推理/数学 | DeepSeek-R1 / Phi-4 | 推理特化 |
| 通用英文 | Llama 3.3 / Gemma 4 | Meta/Google 主力 |

---

## 文件清单

```
backend/
├── app/llm/
│   ├── base.py            # LLMProvider 抽象基类（3 个方法）
│   ├── openai_compat.py   # OpenAI 兼容实现（覆盖 90% 模型）
│   ├── claude.py          # Anthropic Claude 原生实现
│   ├── router.py          # 任务路由 + provider 缓存
│   └── prompts.py         # Prompt 模板集中管理
├── app/config.py          # Pydantic 配置模型 + 环境变量覆盖
└── config.yaml            # 运行时配置（不入 git，含 API key）
```

可直接复制 `app/llm/` 目录到新项目，修改 `config.yaml` 和 `TASK_ROUTING` 即可使用。
