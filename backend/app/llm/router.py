"""LLM 任务路由 — 根据任务类型选择 provider"""

from typing import Optional

from app.config import get_config
from app.llm.base import LLMProvider
from app.llm.claude import ClaudeProvider
from app.llm.openai_compat import OpenAICompatProvider

# 任务类型 → provider 类型映射
TASK_ROUTING = {
    "classify": "local",
    "summarize": "local",
    "segment": "cloud",
    "wiki_generate": "cloud",
    "vision": "vision",
    "query": "cloud",
}

# Provider 单例缓存
_providers: dict[str, LLMProvider] = {}


def _build_provider(provider_type: str, provider_name: str, **kwargs) -> LLMProvider:
    if provider_name == "claude":
        return ClaudeProvider(
            api_key=kwargs["api_key"],
            model=kwargs.get("model", "claude-sonnet-4-6"),
        )
    else:
        # DeepSeek / Kimi / Ollama / OpenAI 都走 OpenAI 兼容接口
        base_url = kwargs["base_url"]
        api_key = kwargs.get("api_key", "ollama")
        if provider_name == "ollama" and not base_url.endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        return OpenAICompatProvider(
            base_url=base_url,
            api_key=api_key,
            model=kwargs["model"],
        )


def get_provider(task: str) -> LLMProvider:
    """根据任务类型获取对应的 LLM provider"""
    cfg = get_config().llm
    provider_type = TASK_ROUTING.get(task, "cloud")

    # 缓存 key
    cache_key = provider_type

    if cache_key not in _providers:
        if provider_type == "cloud":
            _providers[cache_key] = _build_provider(
                "cloud",
                cfg.cloud_provider,
                api_key=cfg.cloud_api_key,
                base_url=cfg.cloud_base_url,
                model=cfg.cloud_model,
            )
        elif provider_type == "local":
            _providers[cache_key] = _build_provider(
                "local",
                cfg.local_provider,
                api_key="ollama",
                base_url=cfg.local_base_url,
                model=cfg.local_model,
            )
        elif provider_type == "vision":
            _providers[cache_key] = _build_provider(
                "vision",
                cfg.vision_provider,
                api_key=cfg.vision_api_key,
                base_url=cfg.cloud_base_url,
                model=cfg.vision_model,
            )

    return _providers[cache_key]


def reset_providers():
    """清除缓存（配置变更后调用）"""
    _providers.clear()
