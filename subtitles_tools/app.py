"""FastAPI 应用工厂。"""

from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from subtitles_tools.api import router
from subtitles_tools.cache import HybridCacheStore
from subtitles_tools.config import AppSettings, get_settings
from subtitles_tools.providers import ProviderError, ProviderTimeoutError, ThunderSubtitleProvider
from subtitles_tools.services import SubtitleNotFoundError, SubtitleService


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """创建 FastAPI 应用。"""

    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """初始化共享依赖并在退出时统一释放。"""

        cache_store = HybridCacheStore(resolved_settings)
        timeout = httpx.Timeout(resolved_settings.upstream_timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": resolved_settings.thunder_user_agent},
        ) as client:
            provider = ThunderSubtitleProvider(client=client, base_url=resolved_settings.thunder_base_url)
            subtitle_service = SubtitleService(
                settings=resolved_settings,
                cache_store=cache_store,
                provider=provider,
            )
            app.state.settings = resolved_settings
            app.state.subtitle_provider = provider
            app.state.subtitle_service = subtitle_service
            yield

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )

    @app.exception_handler(SubtitleNotFoundError)
    async def handle_subtitle_not_found(_: Request, exc: SubtitleNotFoundError) -> JSONResponse:
        """将业务层未命中映射为 404。"""

        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ProviderTimeoutError)
    async def handle_provider_timeout(_: Request, exc: ProviderTimeoutError) -> JSONResponse:
        """将上游超时映射为 504。"""

        return JSONResponse(status_code=504, content={"detail": str(exc)})

    @app.exception_handler(ProviderError)
    async def handle_provider_error(_: Request, exc: ProviderError) -> JSONResponse:
        """将上游异常映射为 502。"""

        return JSONResponse(status_code=502, content={"detail": str(exc)})

    app.include_router(router)
    return app
