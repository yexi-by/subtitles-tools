"""缓存模型定义。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SearchCacheItem(BaseModel):
    """搜索缓存中的字幕项快照。"""

    id: str = Field(description="字幕项稳定标识")
    name: str = Field(description="字幕文件名")
    ext: str = Field(description="字幕扩展名")
    languages: list[str] = Field(default_factory=list, description="字幕语言列表")
    duration_ms: int = Field(description="字幕时长，单位为毫秒")
    source: int = Field(description="字幕来源标识")
    score: int = Field(description="上游原始评分")
    fingerprint_score: float = Field(description="上游指纹评分")
    extra_name: str | None = Field(default=None, description="上游补充说明")


class SearchCacheEntry(BaseModel):
    """搜索结果缓存条目。"""

    matched_by: Literal["gcid", "name"] = Field(description="本次命中的查询方式")
    confidence: Literal["high", "fallback"] = Field(description="本次结果的置信度")
    expires_at: datetime = Field(description="搜索结果过期时间")
    items: list[SearchCacheItem] = Field(default_factory=list, description="缓存的字幕项")


class CachedSubtitleMetadata(BaseModel):
    """字幕代理所需的元数据缓存。"""

    subtitle_id: str = Field(description="字幕项稳定标识")
    provider: str = Field(description="字幕源名称")
    url: str = Field(description="上游字幕下载地址")
    name: str = Field(description="字幕文件名")
    ext: str = Field(description="字幕扩展名")
    expires_at: datetime = Field(description="字幕元数据过期时间")
