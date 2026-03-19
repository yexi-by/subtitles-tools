"""HTTP 接口模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


MatchedBy = Literal["gcid", "name"]
Confidence = Literal["high", "fallback"]
JsonScalar = str | int | float | bool | None


class SearchRequest(BaseModel):
    """字幕搜索请求。"""

    gcid: str | None = Field(default=None, description="媒体文件 GCID")
    cid: str | None = Field(default=None, description="媒体文件 CID")
    name: str | None = Field(default=None, description="媒体文件名")

    @field_validator("gcid", "cid", "name", mode="before")
    @classmethod
    def normalize_text(cls, value: JsonScalar) -> str | None:
        """清理输入字符串。

        这里仅接受 JSON 标量输入。
        请求体若传入对象或数组，保持交给 Pydantic 的字段校验去拒绝，而不是用宽泛类型吞掉问题。
        """

        if value is None:
            return None

        text = str(value).strip()
        if not text:
            return None

        return text

    @field_validator("gcid", "cid")
    @classmethod
    def normalize_hash(cls, value: str | None) -> str | None:
        """统一哈希字段的大小写。"""

        if value is None:
            return None

        return value.upper()

    @model_validator(mode="after")
    def validate_request(self) -> "SearchRequest":
        """确保请求至少具备一个可搜索条件。"""

        if self.gcid is None and self.name is None:
            raise ValueError("gcid 与 name 至少需要提供一个")

        return self


class SearchResponseItem(BaseModel):
    """字幕搜索响应中的单个字幕项。"""

    id: str = Field(description="字幕项稳定标识")
    name: str = Field(description="字幕文件名")
    ext: str = Field(description="字幕扩展名")
    languages: list[str] = Field(default_factory=list, description="字幕语言列表")
    duration_ms: int = Field(description="字幕时长，单位为毫秒")
    source: int = Field(description="字幕来源标识")
    score: int = Field(description="上游返回的原始评分")
    fingerprint_score: float = Field(description="上游返回的指纹评分")
    extra_name: str | None = Field(default=None, description="上游补充说明")
    download_url: str = Field(description="通过本服务代理下载字幕的地址")


class SearchResponse(BaseModel):
    """字幕搜索响应。"""

    matched_by: MatchedBy = Field(description="本次命中的查询方式")
    confidence: Confidence = Field(description="本次结果的置信度")
    items: list[SearchResponseItem] = Field(default_factory=list, description="候选字幕列表")


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = Field(description="服务状态")
    version: str = Field(description="当前服务版本")
    provider_name: str = Field(description="当前启用的字幕源名称")
    provider_available: bool = Field(description="当前字幕源是否可用")
