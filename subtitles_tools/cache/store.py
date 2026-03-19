"""本地缓存实现。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from subtitles_tools.config import AppSettings
from subtitles_tools.models import CachedSubtitleMetadata, DownloadedSubtitle, SearchCacheEntry

type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class HybridCacheStore:
    """内存前置与磁盘落盘并存的缓存实现。"""

    def __init__(self, settings: AppSettings) -> None:
        """初始化缓存目录与内存缓存。"""

        self._settings = settings
        self._search_memory_cache: dict[str, SearchCacheEntry] = {}
        self._subtitle_meta_memory_cache: dict[str, CachedSubtitleMetadata] = {}
        self._subtitle_binary_memory_cache: dict[str, DownloadedSubtitle] = {}
        self._disk_lock = asyncio.Lock()

        self._settings.search_cache_dir.mkdir(parents=True, exist_ok=True)
        self._settings.subtitle_meta_cache_dir.mkdir(parents=True, exist_ok=True)
        self._settings.subtitle_file_cache_dir.mkdir(parents=True, exist_ok=True)

    async def get_search_entry(self, cache_key: str) -> SearchCacheEntry | None:
        """读取搜索结果缓存。"""

        memory_entry = self._search_memory_cache.get(cache_key)
        if memory_entry is not None and not self._is_expired(memory_entry.expires_at):
            return memory_entry

        if memory_entry is not None:
            self._search_memory_cache.pop(cache_key, None)

        file_path = self._search_cache_path(cache_key)
        payload = await self._read_json_file(file_path)
        if payload is None:
            return None

        entry = SearchCacheEntry.model_validate(payload)
        if self._is_expired(entry.expires_at):
            await self._delete_file(file_path)
            return None

        self._search_memory_cache[cache_key] = entry
        return entry

    async def set_search_entry(self, cache_key: str, entry: SearchCacheEntry) -> None:
        """写入搜索结果缓存。"""

        self._search_memory_cache[cache_key] = entry
        await self._write_json_file(self._search_cache_path(cache_key), entry.model_dump(mode="json"))

    async def get_subtitle_metadata(self, subtitle_id: str) -> CachedSubtitleMetadata | None:
        """读取字幕元数据缓存。"""

        memory_entry = self._subtitle_meta_memory_cache.get(subtitle_id)
        if memory_entry is not None and not self._is_expired(memory_entry.expires_at):
            return memory_entry

        if memory_entry is not None:
            self._subtitle_meta_memory_cache.pop(subtitle_id, None)

        file_path = self._subtitle_meta_cache_path(subtitle_id)
        payload = await self._read_json_file(file_path)
        if payload is None:
            return None

        entry = CachedSubtitleMetadata.model_validate(payload)
        if self._is_expired(entry.expires_at):
            await self._delete_file(file_path)
            await self._delete_file(self._subtitle_file_path(entry))
            return None

        self._subtitle_meta_memory_cache[subtitle_id] = entry
        return entry

    async def set_subtitle_metadata(self, metadata: CachedSubtitleMetadata) -> None:
        """写入字幕元数据缓存。"""

        self._subtitle_meta_memory_cache[metadata.subtitle_id] = metadata
        await self._write_json_file(
            self._subtitle_meta_cache_path(metadata.subtitle_id),
            metadata.model_dump(mode="json"),
        )

    async def get_subtitle_content(self, metadata: CachedSubtitleMetadata) -> DownloadedSubtitle | None:
        """读取字幕文件缓存。"""

        memory_entry = self._subtitle_binary_memory_cache.get(metadata.subtitle_id)
        if memory_entry is not None and not self._is_expired(metadata.expires_at):
            return memory_entry

        if memory_entry is not None:
            self._subtitle_binary_memory_cache.pop(metadata.subtitle_id, None)

        file_path = self._subtitle_file_path(metadata)
        if not file_path.exists():
            return None

        if self._is_expired(metadata.expires_at):
            await self._delete_file(file_path)
            return None

        content = await asyncio.to_thread(file_path.read_bytes)
        downloaded = DownloadedSubtitle(
            file_name=metadata.name,
            media_type=self._guess_media_type(metadata.ext),
            content=content,
        )
        self._subtitle_binary_memory_cache[metadata.subtitle_id] = downloaded
        return downloaded

    async def set_subtitle_content(
        self,
        metadata: CachedSubtitleMetadata,
        downloaded: DownloadedSubtitle,
    ) -> None:
        """写入字幕文件缓存。"""

        self._subtitle_binary_memory_cache[metadata.subtitle_id] = downloaded
        file_path = self._subtitle_file_path(metadata)
        async with self._disk_lock:
            await asyncio.to_thread(file_path.write_bytes, downloaded.content)

    def build_search_cache_key(self, gcid: str | None, cid: str | None, name: str | None) -> str:
        """构造稳定的搜索缓存键。"""

        payload = {
            "cid": cid or "",
            "gcid": gcid or "",
            "name": name or "",
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def _search_cache_path(self, cache_key: str) -> Path:
        """返回搜索缓存文件路径。"""

        digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()
        return self._settings.search_cache_dir / f"{digest}.json"

    def _subtitle_meta_cache_path(self, subtitle_id: str) -> Path:
        """返回字幕元数据缓存文件路径。"""

        return self._settings.subtitle_meta_cache_dir / f"{subtitle_id}.json"

    def _subtitle_file_path(self, metadata: CachedSubtitleMetadata) -> Path:
        """返回字幕文件缓存路径。"""

        ext = metadata.ext.lower().lstrip(".")
        return self._settings.subtitle_file_cache_dir / f"{metadata.subtitle_id}.{ext}"

    async def _read_json_file(self, file_path: Path) -> dict[str, JsonValue] | None:
        """读取 JSON 文件。"""

        if not file_path.exists():
            return None

        try:
            content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        except FileNotFoundError:
            return None

        return json.loads(content)

    async def _write_json_file(self, file_path: Path, payload: dict[str, JsonValue]) -> None:
        """写入 JSON 文件。"""

        content = json.dumps(payload, ensure_ascii=False, indent=2)
        async with self._disk_lock:
            await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")

    async def _delete_file(self, file_path: Path) -> None:
        """删除缓存文件。"""

        if not file_path.exists():
            return

        async with self._disk_lock:
            await asyncio.to_thread(file_path.unlink, True)

    def _is_expired(self, expires_at: datetime) -> bool:
        """判断缓存是否已经过期。"""

        return expires_at <= datetime.now(UTC)

    def _guess_media_type(self, ext: str) -> str:
        """根据扩展名推断字幕 MIME 类型。"""

        normalized_ext = ext.lower().lstrip(".")
        media_type_map = {
            "ass": "text/x-ssa; charset=utf-8",
            "srt": "application/x-subrip; charset=utf-8",
            "ssa": "text/x-ssa; charset=utf-8",
            "vtt": "text/vtt; charset=utf-8",
        }
        return media_type_map.get(normalized_ext, "application/octet-stream")
