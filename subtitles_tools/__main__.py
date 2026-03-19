"""命令行启动入口。"""

from __future__ import annotations

import copy

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from .config import get_settings


def main() -> None:
    """启动 FastAPI 服务。

    这里通过工厂函数创建应用，避免导入模块时就提前初始化网络客户端和缓存目录。
    """

    settings = get_settings()
    log_config = copy.deepcopy(LOGGING_CONFIG)
    formatters = log_config.get("formatters")
    if isinstance(formatters, dict):
        default_formatter = formatters.get("default")
        if isinstance(default_formatter, dict):
            default_formatter["fmt"] = (
                "%(asctime)s.%(msecs)03d | %(levelprefix)s %(name)s | %(message)s"
            )
            default_formatter["datefmt"] = "%Y-%m-%d %H:%M:%S"

        access_formatter = formatters.get("access")
        if isinstance(access_formatter, dict):
            access_formatter["fmt"] = (
                "%(asctime)s.%(msecs)03d | %(levelprefix)s %(name)s | "
                '%(client_addr)s - "%(request_line)s" %(status_code)s'
            )
            access_formatter["datefmt"] = "%Y-%m-%d %H:%M:%S"

    root_logger = log_config.get("root")
    if isinstance(root_logger, dict):
        root_logger["level"] = "INFO"
        root_logger["handlers"] = ["default"]

    loggers = log_config.get("loggers")
    if isinstance(loggers, dict):
        subtitles_tools_logger = loggers.get("subtitles_tools")
        if isinstance(subtitles_tools_logger, dict):
            subtitles_tools_logger["level"] = "INFO"
            subtitles_tools_logger["handlers"] = ["default"]
            subtitles_tools_logger["propagate"] = False
        else:
            loggers["subtitles_tools"] = {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            }

    uvicorn.run(
        "subtitles_tools.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        log_config=log_config,
    )


if __name__ == "__main__":
    main()
