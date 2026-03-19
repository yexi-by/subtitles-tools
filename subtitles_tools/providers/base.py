"""字幕源抽象定义。"""

from __future__ import annotations

from typing import Protocol

from subtitles_tools.models import DownloadedSubtitle, ProviderSubtitle


class ProviderError(Exception):
    """上游字幕源返回异常。"""


class ProviderTimeoutError(ProviderError):
    """访问上游字幕源超时。"""


class SubtitleProvider(Protocol):
    """字幕源协议。"""

    provider_name: str

    async def search_by_gcid(self, gcid: str) -> list[ProviderSubtitle]:
        """按 GCID 查询字幕。"""
        ...

    async def search_by_name(self, name: str) -> list[ProviderSubtitle]:
        """按文件名查询字幕。"""
        ...

    async def download_subtitle(
        self, url: str, file_name: str, ext: str
    ) -> DownloadedSubtitle:
        """下载字幕文件。"""
        ...
