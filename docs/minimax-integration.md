# MiniMax M2.7 接入方案

## 概述

PKM 系统第一版本使用 MiniMax M2.7 作为主力 LLM，通过 OpenAI 兼容接口接入。参考了 ShadowDesk 项目的接入方式。

## API 信息

| 项目 | 值 |
|------|-----|
| **API Base URL** | `https://api.minimaxi.com/v1` |
| **模型名称** | `MiniMax-M2.7` |
| **协议** | OpenAI Chat Completions 兼容 |
| **API Key 获取** | [MiniMax 开放平台](https://platform.minimaxi.com/) |
| **支持的端点** | `/v1/chat/completions` |
| **Vision/多模态** | 暂不支持 |

## 接入架构

```
PKM 系统
├── 云端任务（Wiki生成/语义分段/问答）→ MiniMax M2.7
├── 轻量任务（分类/摘要）            → MiniMax M2.7（或 Ollama 本地模型）
└── Vision 图片描述                  → Claude API（MiniMax 暂不支持）
```

**第一版本**：所有文本任务统一走 MiniMax M2.7，Vision 暂不启用（或用 Claude 补充）。

## 关键技术细节

### 1. OpenAI SDK 兼容调用

MiniMax 支持 OpenAI 格式的 Chat Completions API，直接用 `openai` Python SDK：

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url="https://api.minimaxi.com/v1",
    api_key="your-minimax-api-key",
)

response = await client.chat.completions.create(
    model="MiniMax-M2.7",
    messages=[
        {"role": "system", "content": "你是一个文档分类专家。"},
        {"role": "user", "content": "分析以下文档..."},
    ],
    temperature=0.3,
    max_tokens=4096,
)

text = response.choices[0].message.content
```

### 2. 推理块剥离（关键）

MiniMax M2.x 系列模型会在输出中嵌入 `<think>...</think>` 推理块（类似 DeepSeek R1 的思维链）。这些推理内容对最终结果无用，**必须在解析前剥离**，否则 JSON 解析会失败。

```python
import re

_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

def strip_reasoning(text: str) -> str:
    """剥离 MiniMax 输出中的 <think> 推理块"""
    return _THINK_BLOCK_RE.sub("", text).strip()
```

**示例：**

MiniMax 原始输出：
```
<think>
用户让我分析一份 PDF，看起来是技术文档...
我应该识别文档类型和主题标签...
</think>
{"document_type": "technical_doc", "topic_tags": ["API设计", "微服务"]}
```

剥离后：
```json
{"document_type": "technical_doc", "topic_tags": ["API设计", "微服务"]}
```

### 3. JSON 输出清理

LLM 可能在 JSON 外包裹 markdown 代码块，需要额外清理：

```python
def clean_json_text(text: str) -> str:
    text = strip_reasoning(text)       # 先剥离 <think> 块
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)  # 去掉 ```json 开头
    text = re.sub(r"\s*```$", "", text)            # 去掉 ``` 结尾
    return text
```

### 4. Prompt 注意事项

为提高 MiniMax 的 JSON 输出稳定性，在 system prompt 末尾追加：

```
你必须以 JSON 格式输出，不要包含 markdown 代码块标记。不要输出任何思考过程。
```

## 配置方式

### config.yaml

```yaml
llm:
  # 云端 + 本地都用 MiniMax（第一版简化方案）
  cloud_provider: "minimax"
  cloud_model: "MiniMax-M2.7"
  cloud_api_key: "your-minimax-api-key"
  cloud_base_url: "https://api.minimaxi.com/v1"

  local_provider: "minimax"
  local_model: "MiniMax-M2.7"
  local_api_key: "your-minimax-api-key"
  local_base_url: "https://api.minimaxi.com/v1"

  # Vision 暂用 Claude（如不处理图片可留空）
  vision_provider: "claude"
  vision_model: "claude-sonnet-4-6"
  vision_api_key: ""
```

### 任务路由

| 任务 | 路由 | Provider | 说明 |
|------|------|----------|------|
| `classify` | local | MiniMax M2.7 | 文档分类 |
| `summarize` | local | MiniMax M2.7 | 简单摘要 |
| `segment` | cloud | MiniMax M2.7 | 语义分段 |
| `wiki_generate` | cloud | MiniMax M2.7 | Wiki 页面生成 |
| `query` | cloud | MiniMax M2.7 | 问答综合 |
| `vision` | vision | Claude | 图片描述（MiniMax 暂不支持） |

第一版中 cloud 和 local 实际都指向同一个 MiniMax，区分只是为了后续切换方便。

## 代码文件

| 文件 | 说明 |
|------|------|
| `backend/app/llm/openai_compat.py` | OpenAI 兼容 Provider，处理 `<think>` 剥离 |
| `backend/app/llm/router.py` | 任务路由，按任务类型分发到不同 provider |
| `backend/app/config.py` | 配置模型定义，默认 MiniMax |
| `backend/config.example.yaml` | 配置文件模板 |

## 限制与后续

**当前限制：**
- MiniMax 暂不支持 Vision/多模态 → 图片描述需要 Claude 或其他支持的模型
- 推理块剥离基于正则，如果 MiniMax 改变格式需要更新

**后续扩展：**
- 切换到 Ollama 本地模型做轻量任务（节省 API 费用）
- MiniMax 支持 Vision 后统一切换
- 添加 DeepSeek / Kimi 作为备选 provider（只需改 config.yaml）
