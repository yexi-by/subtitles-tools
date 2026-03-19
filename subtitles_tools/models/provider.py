"""字幕源标准模型。"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, Field


class ProviderSubtitle(BaseModel):
    """统一后的字幕源条目。"""

    provider: str = Field(description="字幕源名称")
    url: str = Field(description="上游字幕下载地址")
    gcid: str | None = Field(default=None, description="上游返回的 GCID")
    cid: str | None = Field(default=None, description="上游返回的 CID")
    name: str = Field(description="字幕文件名")
    ext: str = Field(description="字幕扩展名")
    languages: list[str] = Field(default_factory=list, description="字幕语言列表")
    duration_ms: int = Field(default=0, description="字幕时长，单位为毫秒")
    source: int = Field(default=0, description="字幕来源标识")
    score: int = Field(default=0, description="上游原始评分")
    fingerprint_score: float = Field(default=0.0, description="上游指纹评分")
    extra_name: str | None = Field(default=None, description="上游补充说明")


@dataclass(slots=True)
class DownloadedSubtitle:
    """代理下载完成后的字幕文件。"""

    file_name: str
    media_type: str
    content: bytes
