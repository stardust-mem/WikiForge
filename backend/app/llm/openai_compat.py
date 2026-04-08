"""OpenAI 兼容接口 — 适配 DeepSeek / Kimi / Ollama 等"""

import base64
import json
import re
from typing import Any

from openai import AsyncOpenAI

from app.llm.base import LLMProvider


class OpenAICompatProvider(LLMProvider):
    """
    通过 OpenAI SDK 兼容接口调用各种 LLM：
    - DeepSeek: base_url="https://api.deepseek.com"
    - Kimi:     base_url="https://api.moonshot.cn/v1"
    - Ollama:   base_url="http://localhost:11434/v1", api_key="ollama"
    - OpenAI:   base_url="https://api.openai.com/v1"
    """

    def __init__(self, base_url: str, api_key: str, model: str):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

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
                + "\n\n你必须以 JSON 格式输出，不要包含 markdown 代码块标记。",
            }

        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=json_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = resp.choices[0].message.content or "{}"
        # 清理可能的 markdown 代码块包裹
        text = text.strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        return json.loads(text)

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
