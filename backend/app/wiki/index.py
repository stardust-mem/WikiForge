"""index.md 自动维护"""

from datetime import datetime
from pathlib import Path

from app.config import get_wiki_root


def rebuild_index() -> None:
    """扫描 wiki-root 重建 index.md"""
    wiki_root = get_wiki_root()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    categories = {
        "entities": "实体",
        "concepts": "概念",
        "topics": "主题聚合",
        "sources": "文档摘要",
    }

    sections = []
    total_pages = 0

    for cat_key, cat_name in categories.items():
        cat_dir = wiki_root / cat_key
        pages = []
        if cat_dir.exists():
            for md_file in sorted(cat_dir.glob("*.md")):
                # 从文件中提取 title
                title = md_file.stem.replace("-", " ")
                content = md_file.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip('"')
                        break
                pages.append(f"- [[{cat_key}/{md_file.stem}|{title}]]")
                total_pages += 1

        count = len(pages)
        section = f"## {cat_name}（{count}页）\n\n"
        if pages:
            section += "\n".join(pages)
        else:
            section += "_暂无内容_"
        sections.append(section)

    topic_count = len(list((wiki_root / "topics").glob("*.md"))) if (wiki_root / "topics").exists() else 0

    index_content = f"""# 知识目录

> 自动维护，最后更新：{now} | 共 {total_pages} 页 | {topic_count} 个主题

{"".join(chr(10) + chr(10) + s for s in sections)}
"""

    index_path = wiki_root / "index.md"
    index_path.write_text(index_content.strip() + "\n", encoding="utf-8")
