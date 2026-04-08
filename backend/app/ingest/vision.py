"""图片描述 — Vision API 封装"""

from app.llm.router import get_provider
from app.llm.prompts import VISION_CHART, VISION_DIAGRAM, VISION_GENERAL


async def describe_image(
    image_bytes: bytes,
    media_type: str = "image/png",
    hint: str = "general",
) -> str:
    """
    用 Vision API 描述图片。

    hint: "chart" | "diagram" | "general"
    """
    provider = get_provider("vision")

    prompt_map = {
        "chart": VISION_CHART,
        "diagram": VISION_DIAGRAM,
        "general": VISION_GENERAL,
    }
    prompt = prompt_map.get(hint, VISION_GENERAL)

    description = await provider.vision(
        image_bytes=image_bytes,
        prompt=prompt,
        media_type=media_type,
    )
    return description
