"""LLM Provider 抽象基类"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class LLMProvider(ABC):
    """所有 LLM provider 的统一接口"""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> str:
        """普通对话，返回文本"""
        ...

    @abstractmethod
    async def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """对话并返回 JSON（自动 parse）"""
        ...

    async def vision(
        self,
        image_bytes: bytes,
        prompt: str,
        media_type: str = "image/png",
        max_tokens: int = 1024,
    ) -> str:
        """图片描述（默认不支持，子类按需覆盖）"""
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 Vision")
