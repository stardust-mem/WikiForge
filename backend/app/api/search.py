"""搜索 & 问答 API（Phase 3 实现，先放 stub）"""

from fastapi import APIRouter

from app.models.schemas import SearchRequest, SearchResult, QueryRequest, QueryResponse

router = APIRouter()


@router.post("/search", response_model=list[SearchResult])
async def search_wiki(req: SearchRequest):
    """搜索 Wiki 页面（Phase 3 实现）"""
    return []


@router.post("/query", response_model=QueryResponse)
async def query_wiki(req: QueryRequest):
    """问答（Phase 3 实现）"""
    return QueryResponse(
        answer="问答功能尚未实现，请先导入文档。",
        citations=[],
    )
