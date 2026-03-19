"""FastAPI 应用工厂。"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from subtitles_tools.api import router
from subtitles_tools.cache import HybridCacheStore
from subtitles_tools.config import AppSettings, get_settings
from subtitles_tools.providers import ProviderError, ProviderTimeoutError, ThunderSubtitleProvider
from subtitles_tools.services import SubtitleNotFoundError, SubtitleService

LOGGER = logging.getLogger(__name__)


def _get_trace_id(request: Request) -> str:
    """从请求状态中提取链路追踪标识。"""

    trace_id_value = getattr(request.state, "trace_id", None)
    if isinstance(trace_id_value, str) and trace_id_value:
        return trace_id_value

    return "-"


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
            LOGGER.info(
                "service_start host=%s port=%d thunder_base_url=%s cache_dir=%s",
                resolved_settings.host,
                resolved_settings.port,
                resolved_settings.thunder_base_url,
                resolved_settings.cache_dir,
            )
            yield
            LOGGER.info("service_stop")

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def trace_request(request: Request, call_next):
        """为每个请求附加追踪标识并记录总耗时。"""

        incoming_trace_id = request.headers.get("X-Subtitles-Trace-Id", "").strip()
        trace_id = incoming_trace_id or uuid.uuid4().hex[:12]
        request.state.trace_id = trace_id
        started_at = time.perf_counter()
        LOGGER.info("trace=%s http_start method=%s path=%s", trace_id, request.method, request.url.path)

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started_at) * 1000
            LOGGER.exception(
                "trace=%s http_exception method=%s path=%s total_ms=%.2f",
                trace_id,
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise

        response.headers["X-Subtitles-Trace-Id"] = trace_id
        elapsed_ms = (time.perf_counter() - started_at) * 1000
        LOGGER.info(
            "trace=%s http_complete method=%s path=%s status=%d total_ms=%.2f",
            trace_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response

    @app.exception_handler(SubtitleNotFoundError)
    async def handle_subtitle_not_found(request: Request, exc: SubtitleNotFoundError) -> JSONResponse:
        """将业务层未命中映射为 404。"""

        return JSONResponse(
            status_code=404,
            content={"detail": str(exc)},
            headers={"X-Subtitles-Trace-Id": _get_trace_id(request)},
        )

    @app.exception_handler(ProviderTimeoutError)
    async def handle_provider_timeout(request: Request, exc: ProviderTimeoutError) -> JSONResponse:
        """将上游超时映射为 504。"""

        return JSONResponse(
            status_code=504,
            content={"detail": str(exc)},
            headers={"X-Subtitles-Trace-Id": _get_trace_id(request)},
        )

    @app.exception_handler(ProviderError)
    async def handle_provider_error(request: Request, exc: ProviderError) -> JSONResponse:
        """将上游异常映射为 502。"""

        return JSONResponse(
            status_code=502,
            content={"detail": str(exc)},
            headers={"X-Subtitles-Trace-Id": _get_trace_id(request)},
        )

    app.include_router(router)
    return app
