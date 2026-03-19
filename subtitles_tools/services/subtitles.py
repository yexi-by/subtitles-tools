"""字幕搜索与代理下载服务。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

from subtitles_tools.cache import HybridCacheStore
from subtitles_tools.config import AppSettings
from subtitles_tools.models import (
    CachedSubtitleMetadata,
    DownloadedSubtitle,
    ProviderSubtitle,
    SearchCacheEntry,
    SearchCacheItem,
    SearchRequest,
)
from subtitles_tools.providers import SubtitleProvider


class SubtitleNotFoundError(Exception):
    """请求了不存在的字幕项。"""


class SubtitleService:
    """字幕搜索与下载业务入口。"""

    def __init__(
        self,
        settings: AppSettings,
        cache_store: HybridCacheStore,
        provider: SubtitleProvider,
    ) -> None:
        """初始化服务对象。"""

        self._settings = settings
        self._cache_store = cache_store
        self._provider = provider

    async def search_subtitles(self, payload: SearchRequest) -> SearchCacheEntry:
        """搜索字幕并返回缓存格式的结果。"""

        cache_key = self._cache_store.build_search_cache_key(payload.gcid, payload.cid, payload.name)
        cached_entry = await self._cache_store.get_search_entry(cache_key)
        if cached_entry is not None:
            return cached_entry

        matched_by = "gcid"
        confidence = "high"
        provider_items: list[ProviderSubtitle] = []

        if payload.gcid is not None:
            provider_items = await self._provider.search_by_gcid(payload.gcid)

        if not provider_items and payload.name is not None:
            matched_by = "name"
            confidence = "fallback" if payload.gcid is not None else "high"
            provider_items = await self._provider.search_by_name(payload.name)

        normalized_items = self._normalize_items(provider_items)
        search_entry = SearchCacheEntry(
            matched_by=matched_by,
            confidence=confidence,
            expires_at=self._search_expires_at(),
            items=[item for item, _ in normalized_items],
        )
        await self._cache_store.set_search_entry(cache_key, search_entry)

        for _, metadata in normalized_items:
            await self._cache_store.set_subtitle_metadata(metadata)

        return search_entry

    async def download_subtitle(self, subtitle_id: str) -> DownloadedSubtitle:
        """代理下载指定字幕。"""

        metadata = await self._cache_store.get_subtitle_metadata(subtitle_id)
        if metadata is None:
            raise SubtitleNotFoundError("字幕不存在或缓存已过期")

        cached_download = await self._cache_store.get_subtitle_content(metadata)
        if cached_download is not None:
            return cached_download

        downloaded = await self._provider.download_subtitle(metadata.url, metadata.name, metadata.ext)
        await self._cache_store.set_subtitle_content(metadata, downloaded)
        return downloaded

    def _normalize_items(
        self,
        provider_items: list[ProviderSubtitle],
    ) -> list[tuple[SearchCacheItem, CachedSubtitleMetadata]]:
        """去重并规范化 provider 结果。"""

        best_items_by_url: dict[str, ProviderSubtitle] = {}
        for item in provider_items:
            current_best = best_items_by_url.get(item.url)
            if current_best is None:
                best_items_by_url[item.url] = item
                continue

            if self._rank_item(item) > self._rank_item(current_best):
                best_items_by_url[item.url] = item

        ordered_items = sorted(best_items_by_url.values(), key=self._rank_item, reverse=True)
        normalized_items: list[tuple[SearchCacheItem, CachedSubtitleMetadata]] = []
        for item in ordered_items:
            subtitle_id = self._build_subtitle_id(item)
            normalized_items.append(
                (
                    SearchCacheItem(
                        id=subtitle_id,
                        name=item.name,
                        ext=item.ext,
                        languages=item.languages,
                        duration_ms=item.duration_ms,
                        source=item.source,
                        score=item.score,
                        fingerprint_score=item.fingerprint_score,
                        extra_name=item.extra_name,
                    ),
                    CachedSubtitleMetadata(
                        subtitle_id=subtitle_id,
                        provider=item.provider,
                        url=item.url,
                        name=item.name,
                        ext=item.ext,
                        expires_at=self._subtitle_expires_at(),
                    ),
                ),
            )

        return normalized_items

    def _build_subtitle_id(self, item: ProviderSubtitle) -> str:
        """生成稳定的字幕项标识。"""

        raw = f"{item.provider}|{item.url}|{item.name}|{item.ext}"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()

    def _rank_item(self, item: ProviderSubtitle) -> tuple[int, float, int, int]:
        """为字幕项生成排序权重。"""

        return (
            item.score,
            item.fingerprint_score,
            len(item.languages),
            item.duration_ms,
        )

    def _search_expires_at(self) -> datetime:
        """计算搜索缓存过期时间。"""

        return datetime.now(UTC) + timedelta(seconds=self._settings.search_cache_ttl_seconds)

    def _subtitle_expires_at(self) -> datetime:
        """计算字幕元数据与文件缓存过期时间。"""

        return datetime.now(UTC) + timedelta(seconds=self._settings.subtitle_cache_ttl_seconds)
