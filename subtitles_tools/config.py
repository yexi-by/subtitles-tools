"""应用配置定义。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict, TomlConfigSettingsSource


class AppSettings(BaseSettings):
    """服务端运行配置。

    当前配置以 `setting.toml` 为主，环境变量作为覆盖层。
    这样既适合本地部署，也方便 Docker 场景按环境覆盖少量敏感参数。
    """

    app_name: str = Field(default="subtitles-tools", description="应用名称")
    app_version: str = Field(default="0.1.0", description="应用版本")
    host: str = Field(default="0.0.0.0", description="服务监听地址")
    port: int = Field(default=8055, description="服务监听端口")
    thunder_base_url: str = Field(
        default="https://api-shoulei-ssl.xunlei.com",
        description="迅雷字幕接口根地址",
    )
    thunder_user_agent: str = Field(
        default="subtitles-tools/0.1.0",
        description="访问迅雷接口时使用的 User-Agent",
    )
    upstream_timeout_seconds: float = Field(
        default=10.0,
        description="访问上游接口的超时时间",
    )
    data_dir: Path = Field(default=Path("data"), description="服务运行数据目录")
    search_cache_ttl_seconds: int = Field(
        default=24 * 60 * 60,
        description="搜索结果缓存有效期，单位为秒",
    )
    subtitle_cache_ttl_seconds: int = Field(
        default=7 * 24 * 60 * 60,
        description="字幕元数据与文件缓存有效期，单位为秒",
    )

    model_config = SettingsConfigDict(
        env_prefix="SUBTITLES_TOOLS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """自定义配置加载顺序。

        将 `setting.toml` 放在环境变量之后、内置默认值之前。
        这样本地默认使用文件配置，部署时仍可通过环境变量临时覆盖。
        """

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls, toml_file="setting.toml"),
            file_secret_settings,
        )

    @property
    def cache_dir(self) -> Path:
        """返回缓存根目录。"""

        return self.data_dir / "cache"

    @property
    def search_cache_dir(self) -> Path:
        """返回搜索结果缓存目录。"""

        return self.cache_dir / "search"

    @property
    def subtitle_meta_cache_dir(self) -> Path:
        """返回字幕元数据缓存目录。"""

        return self.cache_dir / "subtitle_meta"

    @property
    def subtitle_file_cache_dir(self) -> Path:
        """返回字幕文件缓存目录。"""

        return self.cache_dir / "subtitle_files"


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """返回缓存后的配置对象。"""

    return AppSettings()
