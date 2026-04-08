"""Claude (Anthropic) Provider"""

import base64
import json
import re
from typing import Any

import anthropic

from app.llm.base import LLMProvider


class ClaudeProvider(LLMProvider):
    """Anthropic Claude API — 原生 SDK，支持 Vision"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model = model

    def _convert_messages(
        self, messages: list[dict[str, str]]
    ) -> tuple[str, list[dict]]:
        """将 OpenAI 格式的 messages 转为 Anthropic 格式（system 分离）"""
        system = ""
        converted = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                converted.append({"role": msg["role"], "content": msg["content"]})
        return system, converted

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        system, msgs = self._convert_messages(messages)
        resp = await self.client.messages.create(
            model=self.model,
            system=system,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.content[0].text

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        system, msgs = self._convert_messages(messages)
        system += "\n\n你必须以 JSON 格式输出，不要包含 markdown 代码块标记。"

        resp = await self.client.messages.create(
            model=self.model,
            system=system,
            messages=msgs,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        text = resp.content[0].text.strip()
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
        b64 = base64.b64encode(image_bytes).decode()
        resp = await self.client.messages.create(
            model=self.model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_tokens=max_tokens,
        )
        return resp.content[0].text
