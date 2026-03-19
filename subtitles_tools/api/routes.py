"""HTTP 路由定义。"""

from __future__ import annotations

import logging
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response

from subtitles_tools.models import HealthResponse, SearchRequest, SearchResponse, SearchResponseItem
from subtitles_tools.services import SubtitleService

router = APIRouter()
LOGGER = logging.getLogger(__name__)


def get_subtitle_service(request: Request) -> SubtitleService:
    """从应用状态中提取字幕服务对象。"""

    return request.app.state.subtitle_service


def get_trace_id(request: Request) -> str:
    """读取请求上下文中的追踪标识。"""

    trace_id_value = getattr(request.state, "trace_id", None)
    if isinstance(trace_id_value, str) and trace_id_value:
        return trace_id_value

    return "-"


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """返回服务健康状态。"""

    settings = request.app.state.settings
    provider = request.app.state.subtitle_provider
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        provider_name=provider.provider_name,
        provider_available=True,
    )


@router.post("/api/v1/subtitles/search", response_model=SearchResponse)
async def search_subtitles(
    payload: SearchRequest,
    request: Request,
    service: SubtitleService = Depends(get_subtitle_service),
) -> SearchResponse:
    """搜索字幕候选列表。"""

    trace_id = get_trace_id(request)
    started_at = time.perf_counter()
    LOGGER.info(
        "trace=%s route_search_start gcid=%s cid=%s name=%s",
        trace_id,
        payload.gcid or "-",
        payload.cid or "-",
        payload.name or "-",
    )
    search_result = await service.search_subtitles(payload, trace_id=trace_id)
    items = [
        SearchResponseItem(
            id=item.id,
            name=item.name,
            ext=item.ext,
            languages=item.languages,
            duration_ms=item.duration_ms,
            source=item.source,
            score=item.score,
            fingerprint_score=item.fingerprint_score,
            extra_name=item.extra_name,
            download_url=str(request.url_for("download_subtitle", subtitle_id=item.id)),
        )
        for item in search_result.items
    ]
    return SearchResponse(
        matched_by=search_result.matched_by,
        confidence=search_result.confidence,
        items=items,
    )
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    LOGGER.info(
        "trace=%s route_search_complete matched_by=%s confidence=%s items=%d total_ms=%.2f",
        trace_id,
        search_result.matched_by,
        search_result.confidence,
        len(items),
        elapsed_ms,
    )
    return response_payload


@router.get("/api/v1/subtitles/{subtitle_id}", name="download_subtitle")
async def download_subtitle(
    subtitle_id: str,
    request: Request,
    service: SubtitleService = Depends(get_subtitle_service),
) -> Response:
    """代理下载字幕文件。"""

    trace_id = get_trace_id(request)
    started_at = time.perf_counter()
    LOGGER.info("trace=%s route_download_start subtitle_id=%s", trace_id, subtitle_id)
    subtitle = await service.download_subtitle(subtitle_id, trace_id=trace_id)
    encoded_file_name = quote(subtitle.file_name, safe="")
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"subtitle\"; filename*=UTF-8''{encoded_file_name}"
        )
    }
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    LOGGER.info(
        "trace=%s route_download_complete subtitle_id=%s bytes=%d total_ms=%.2f",
        trace_id,
        subtitle_id,
        len(subtitle.content),
        elapsed_ms,
    )
    return Response(content=subtitle.content, media_type=subtitle.media_type, headers=headers)
