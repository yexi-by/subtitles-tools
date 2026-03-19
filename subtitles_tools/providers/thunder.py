"""迅雷字幕源实现。"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import httpx
from pydantic import BaseModel, Field

from subtitles_tools.models import DownloadedSubtitle, ProviderSubtitle
from subtitles_tools.providers.base import ProviderError, ProviderTimeoutError

LOGGER = logging.getLogger(__name__)


class ThunderSubtitlePayload(BaseModel):
    """迅雷接口返回的单个字幕项。"""

    gcid: str | None = Field(default=None)
    cid: str | None = Field(default=None)
    url: str
    ext: str
    name: str
    duration: int = Field(default=0)
    languages: list[str] = Field(default_factory=list)
    source: int = Field(default=0)
    score: int = Field(default=0)
    fingerprintf_score: float = Field(default=0.0)
    extra_name: str | None = Field(default=None)


class ThunderSearchResponse(BaseModel):
    """迅雷字幕接口响应体。"""

    code: int
    data: list[ThunderSubtitlePayload] = Field(default_factory=list)
    result: str


class ThunderSubtitleProvider:
    """迅雷在线字幕 provider。"""

    provider_name = "thunder"

    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        """初始化迅雷 provider。"""

        self._client = client
        self._base_url = base_url.rstrip("/")

    async def search_by_gcid(
        self,
        gcid: str,
        trace_id: str | None = None,
    ) -> list[ProviderSubtitle]:
        """按 GCID 查询字幕。"""

        return await self._search({"gcid": gcid}, trace_id=trace_id)

    async def search_by_name(
        self,
        name: str,
        trace_id: str | None = None,
    ) -> list[ProviderSubtitle]:
        """按文件名查询字幕。"""

        return await self._search({"name": name}, trace_id=trace_id)

    async def download_subtitle(
        self,
        url: str,
        file_name: str,
        ext: str,
        trace_id: str | None = None,
    ) -> DownloadedSubtitle:
        """下载上游字幕文件。"""

        trace_label = trace_id or "-"
        started_at = time.perf_counter()
        try:
            response = await self._client.get(url)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            LOGGER.warning(
                "trace=%s thunder_download_timeout url=%s total_ms=%.2f",
                trace_label,
                url,
                elapsed_ms,
            )
            raise ProviderTimeoutError("下载迅雷字幕超时") from exc
        except httpx.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            LOGGER.warning(
                "trace=%s thunder_download_failed url=%s total_ms=%.2f",
                trace_label,
                url,
                elapsed_ms,
            )
            raise ProviderError("下载迅雷字幕失败") from exc

        media_type = response.headers.get("Content-Type")
        if media_type is None:
            media_type = self._guess_media_type(ext)

        elapsed_ms = (time.perf_counter() - started_at) * 1000
        LOGGER.info(
            "trace=%s thunder_download_complete url=%s bytes=%d total_ms=%.2f",
            trace_label,
            url,
            len(response.content),
            elapsed_ms,
        )

        return DownloadedSubtitle(
            file_name=file_name,
            media_type=media_type,
            content=response.content,
        )

    async def _search(
        self,
        params: dict[str, str],
        trace_id: str | None = None,
    ) -> list[ProviderSubtitle]:
        """访问迅雷字幕搜索接口。"""

        trace_label = trace_id or "-"
        query_mode = next(iter(params), "unknown")
        started_at = time.perf_counter()
        try:
            response = await self._client.get(f"{self._base_url}/oracle/subtitle", params=params)
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            LOGGER.warning(
                "trace=%s thunder_search_timeout mode=%s total_ms=%.2f",
                trace_label,
                query_mode,
                elapsed_ms,
            )
            raise ProviderTimeoutError("访问迅雷字幕接口超时") from exc
        except httpx.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            LOGGER.warning(
                "trace=%s thunder_search_failed mode=%s total_ms=%.2f",
                trace_label,
                query_mode,
                elapsed_ms,
            )
            raise ProviderError("访问迅雷字幕接口失败") from exc

        try:
            payload = ThunderSearchResponse.model_validate(response.json())
        except Exception as exc:  # noqa: BLE001
            raise ProviderError("迅雷字幕接口返回了无法解析的数据") from exc

        if payload.code != 0 or payload.result != "ok":
            raise ProviderError("迅雷字幕接口返回了失败状态")

        items = [self._normalize_item(item) for item in payload.data if item.url]
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        LOGGER.info(
            "trace=%s thunder_search_complete mode=%s items=%d total_ms=%.2f",
            trace_label,
            query_mode,
            len(items),
            elapsed_ms,
        )
        return items

    def _normalize_item(self, item: ThunderSubtitlePayload) -> ProviderSubtitle:
        """将迅雷原始字段映射为统一模型。"""

        languages = [language for language in item.languages if language]
        ext = item.ext.lower().lstrip(".")

        return ProviderSubtitle(
            provider=self.provider_name,
            url=item.url,
            gcid=item.gcid,
            cid=item.cid,
            name=item.name,
            ext=ext,
            languages=languages,
            duration_ms=item.duration,
            source=item.source,
            score=item.score,
            fingerprint_score=item.fingerprintf_score,
            extra_name=item.extra_name,
        )

    def _guess_media_type(self, ext: str) -> str:
        """根据扩展名推断字幕 MIME 类型。"""

        normalized_ext = Path(f"file.{ext}").suffix.lower()
        media_type_map = {
            ".ass": "text/x-ssa; charset=utf-8",
            ".srt": "application/x-subrip; charset=utf-8",
            ".ssa": "text/x-ssa; charset=utf-8",
            ".vtt": "text/vtt; charset=utf-8",
        }
        return media_type_map.get(normalized_ext, "application/octet-stream")
