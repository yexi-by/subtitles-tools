"""HTTP 路由定义。"""

from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, Response

from subtitles_tools.models import HealthResponse, SearchRequest, SearchResponse, SearchResponseItem
from subtitles_tools.services import SubtitleService

router = APIRouter()


def get_subtitle_service(request: Request) -> SubtitleService:
    """从应用状态中提取字幕服务对象。"""

    return request.app.state.subtitle_service


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

    search_result = await service.search_subtitles(payload)
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


@router.get("/api/v1/subtitles/{subtitle_id}", name="download_subtitle")
async def download_subtitle(
    subtitle_id: str,
    service: SubtitleService = Depends(get_subtitle_service),
) -> Response:
    """代理下载字幕文件。"""

    subtitle = await service.download_subtitle(subtitle_id)
    encoded_file_name = quote(subtitle.file_name, safe="")
    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"subtitle\"; filename*=UTF-8''{encoded_file_name}"
        )
    }
    return Response(content=subtitle.content, media_type=subtitle.media_type, headers=headers)
