"""PDF 文档提取 — pdfplumber + Vision API 处理图片"""

import io
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber
from PIL import Image


@dataclass
class ExtractedPage:
    page_num: int
    text: str
    images: list[bytes] = field(default_factory=list)
    image_types: list[str] = field(default_factory=list)
    is_image_page: bool = False


@dataclass
class PDFExtractResult:
    pages: list[ExtractedPage]
    total_pages: int
    total_text: str
    has_images: bool


def extract_pdf(file_path: Path) -> PDFExtractResult:
    """
    提取 PDF 内容：文字层 + 图片。

    策略：
    - 有文字层 → pdfplumber 提取文字
    - 每页文字 < 50 字符 → 判定为图片型页面，需 Vision 处理
    - 图片提取为 bytes，后续送 Vision API
    """
    pages = []
    all_text_parts = []

    with pdfplumber.open(str(file_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            images = []
            image_types = []

            # 提取页面中的图片
            for img_info in page.images:
                try:
                    # pdfplumber 的 images 是坐标信息，需要裁剪
                    bbox = (
                        img_info["x0"],
                        img_info["top"],
                        img_info["x1"],
                        img_info["bottom"],
                    )
                    cropped = page.crop(bbox)
                    pil_img = cropped.to_image(resolution=150).original
                    buf = io.BytesIO()
                    pil_img.save(buf, format="PNG")
                    img_bytes = buf.getvalue()
                    # 跳过太小的图片（装饰性）
                    if len(img_bytes) > 5000:
                        images.append(img_bytes)
                        image_types.append("image/png")
                except Exception:
                    continue

            is_image_page = len(text.strip()) < 50 and len(images) > 0

            pages.append(
                ExtractedPage(
                    page_num=i + 1,
                    text=text,
                    images=images,
                    image_types=image_types,
                    is_image_page=is_image_page,
                )
            )
            all_text_parts.append(text)

    total_text = "\n\n".join(all_text_parts)
    has_images = any(len(p.images) > 0 for p in pages)

    return PDFExtractResult(
        pages=pages,
        total_pages=len(pages),
        total_text=total_text,
        has_images=has_images,
    )
