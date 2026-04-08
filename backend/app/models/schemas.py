"""Pydantic 请求/响应模型"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# --- Ingest ---

class IngestResponse(BaseModel):
    source_id: str
    filename: str
    document_type: str
    topic_tags: list[str]
    summary: str
    wiki_pages_created: list[str]
    wiki_pages_updated: list[str]


# --- Wiki ---

class WikiPageSummary(BaseModel):
    page_id: str
    title: str
    category: str
    last_updated: Optional[datetime] = None
    source_count: int = 0


class WikiPageDetail(BaseModel):
    page_id: str
    title: str
    category: str
    content: str
    created_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    source_count: int = 0
    related_pages: list[str] = []


class WikiTree(BaseModel):
    """Wiki 目录树"""
    category: str
    pages: list[WikiPageSummary]


# --- Search ---

class SearchRequest(BaseModel):
    query: str
    top_k: int = 7


class SearchResult(BaseModel):
    page_id: str
    title: str
    snippet: str
    score: float


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str
    citations: list[str]
    suggested_page: Optional[dict] = None


# --- Classification ---

class ClassificationResult(BaseModel):
    document_type: str
    confidence: float
    topic_tags: list[str]
    primary_topic: str
    language: str
    time_period: Optional[str] = None
    entities: list[str]
    summary_one_line: str


# --- Segment ---

class Segment(BaseModel):
    segment_id: str
    title: Optional[str] = None
    summary: Optional[str] = None
    content: str
    token_count: int = 0
    parent_segment_id: Optional[str] = None
