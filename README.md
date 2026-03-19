# subtitles-tools

`subtitles-tools` 是给 Jellyfin 字幕增强插件使用的 Python 服务端。当前版本只接入迅雷在线字幕接口，负责接收客户端上传的 `gcid`、`cid`、`name`，返回候选字幕列表，并通过本服务代理下载字幕内容。

Jellyfin 客户端插件仓库：
<https://github.com/yexi-by/jellyfin-plugin-subtitles-tools>

Jellyfin 插件仓库 manifest：
<https://raw.githubusercontent.com/yexi-by/jellyfin-plugin-subtitles-tools/main/manifest/stable.json>

## 当前边界

- 当前只实现 Python 服务端，不包含 C# 客户端代码
- 当前只支持一个字幕源：迅雷
- 不提供本地文件扫描，也不在服务端计算 `GCID/CID`
- 默认部署目标是可信局域网，不建议直接暴露到公网

## 配置

服务默认从项目根目录的 `setting.toml` 读取配置。默认监听地址是 `0.0.0.0:8055`。

## 本地运行

```bash
uv sync --python 3.13
uv run subtitles-tools
```

## Docker Compose

```bash
docker compose up -d --build
```

默认会挂载：

- `./setting.toml` 到容器内 `/app/setting.toml`
- `./data` 到容器内 `/app/data`

## 接口

- `GET /health`
- `POST /api/v1/subtitles/search`
- `GET /api/v1/subtitles/{subtitle_id}`

## 测试

```bash
uv run pytest
```
