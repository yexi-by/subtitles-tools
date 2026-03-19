"""命令行启动入口。"""

from __future__ import annotations

import uvicorn

from .config import get_settings


def main() -> None:
    """启动 FastAPI 服务。

    这里通过工厂函数创建应用，避免导入模块时就提前初始化网络客户端和缓存目录。
    """

    settings = get_settings()
    uvicorn.run(
        "subtitles_tools.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()
