"""OpenAI 兼容接口 — 适配 MiniMax / DeepSeek / Kimi / Ollama 等"""

import asyncio
import base64
import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI

from app.llm.base import LLMProvider, LLMOutputError

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# MiniMax M2.x 模型会在输出中嵌入 <think>...</think> 推理块，需要剥离
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_reasoning(text: str) -> str:
    """剥离 MiniMax 等模型输出中的 <think> 推理块"""
    return _THINK_BLOCK_RE.sub("", text).strip()


def _clean_json_text(text: str) -> str:
    """清理 LLM 输出中的干扰内容，提取纯 JSON"""
    text = _strip_reasoning(text)
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text


class OpenAICompatProvider(LLMProvider):
    """
    通过 OpenAI SDK 兼容接口调用各种 LLM：
    - MiniMax:  base_url="https://api.minimaxi.com/v1"
    - DeepSeek: base_url="https://api.deepseek.com"
    - Kimi:     base_url="https://api.moonshot.cn/v1"
    - Ollama:   base_url="http://localhost:11434/v1", api_key="ollama"
    - OpenAI:   base_url="https://api.openai.com/v1"
    """

    def __init__(self, base_url: str, api_key: str, model: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    async def _call_with_retry(self, messages, temperature, max_tokens):
        """带重试的 API 调用（处理 500/超时等临时错误）"""
        last_err = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp
            except Exception as e:
                last_err = e
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (attempt + 1)
                    logger.warning(f"LLM API error (attempt {attempt+1}): {e}, retrying in {delay}s")
                    await asyncio.sleep(delay)
        raise last_err

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        resp = await self._call_with_retry(messages, temperature, max_tokens)
        text = resp.choices[0].message.content or ""
        return _strip_reasoning(text)

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        # 在 system 消息中加上 JSON 输出要求
        json_messages = list(messages)
        if json_messages and json_messages[0]["role"] == "system":
            json_messages[0] = {
                **json_messages[0],
                "content": json_messages[0]["content"]
                + "\n\n你必须以 JSON 格式输出，不要包含 markdown 代码块标记。不要输出任何思考过程。",
            }

        resp = await self._call_with_retry(json_messages, temperature, max_tokens)
        text = resp.choices[0].message.content or "{}"
        text = _clean_json_text(text)
        try:
            return json.loads(text, strict=False)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start:end + 1], strict=False)
                except json.JSONDecodeError:
                    pass
            raise LLMOutputError(
                f"LLM did not return valid JSON: {text[:200]}"
            )

    async def vision(
        self,
        image_bytes: bytes,
        prompt: str,
        media_type: str = "image/png",
        max_tokens: int = 1024,
    ) -> str:
        """通过 OpenAI 兼容的 vision 接口处理图片"""
        b64 = base64.b64encode(image_bytes).decode()
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{b64}",
                            },
                        },
                    ],
                }
            ],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
