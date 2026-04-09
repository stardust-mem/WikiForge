"""Git 自动提交 wiki 变更"""
import logging
from pathlib import Path
from app.config import get_wiki_root

logger = logging.getLogger(__name__)


def auto_commit(message: str) -> bool:
    """对 wiki-root 目录执行 git add + commit。返回是否成功。"""
    try:
        import git
        wiki_root = get_wiki_root()
        # repo root is wiki-root's parent's parent (PersonalWiki/)
        repo_root = wiki_root.parent.parent
        repo = git.Repo(str(repo_root))

        # Stage all wiki-root changes
        repo.index.add([str(p) for p in wiki_root.rglob("*.md")])

        if repo.is_dirty(index=True):
            repo.index.commit(message)
            logger.info(f"Git commit: {message}")
            return True
        return False
    except Exception as e:
        logger.warning(f"Git auto-commit failed: {e}")
        return False
