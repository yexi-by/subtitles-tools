"""API 行为测试。"""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

import httpx
import respx
from fastapi.testclient import TestClient

from subtitles_tools.app import create_app
from subtitles_tools.config import AppSettings


class ThunderMockSubtitleItem(TypedDict):
    """迅雷字幕接口测试用的单条字幕项。"""

    gcid: str
    cid: str
    url: str
    ext: str
    name: str
    duration: int
    languages: list[str]
    source: int
    score: int
    fingerprintf_score: float
    extra_name: str


class ThunderMockSearchResponse(TypedDict):
    """迅雷字幕接口测试用的响应体。"""

    code: int
    result: str
    data: list[ThunderMockSubtitleItem]


def build_settings(data_dir: Path) -> AppSettings:
    """构造测试配置。"""

    return AppSettings(
        data_dir=data_dir,
        thunder_base_url="https://api-shoulei-ssl.xunlei.com",
        upstream_timeout_seconds=1.0,
    )


def build_search_payload(
    url: str,
    *,
    score: int = 100,
    fingerprint_score: float = 88.8,
) -> ThunderMockSearchResponse:
    """构造迅雷字幕接口返回数据。"""

    return {
        "code": 0,
        "result": "ok",
        "data": [
            {
                "gcid": "GCID-ONE",
                "cid": "CID-ONE",
                "url": url,
                "ext": "srt",
                "name": "测试字幕.srt",
                "duration": 123456,
                "languages": ["chi", "eng"],
                "source": 1,
                "score": score,
                "fingerprintf_score": fingerprint_score,
                "extra_name": "网友上传",
            }
        ],
    }


def test_search_requires_gcid_or_name(tmp_path: Path) -> None:
    """缺少必要搜索条件时返回 422。"""

    with TestClient(create_app(build_settings(tmp_path / "data"))) as client:
        response = client.post("/api/v1/subtitles/search", json={"cid": "CID"})

    assert response.status_code == 422


def test_search_by_gcid_success(tmp_path: Path) -> None:
    """GCID 命中时只返回 GCID 查询结果。"""

    settings = build_settings(tmp_path / "data")
    with respx.mock(assert_all_called=True, assert_all_mocked=True) as mock_router:
        gcid_route = mock_router.get(
            "https://api-shoulei-ssl.xunlei.com/oracle/subtitle",
            params={"gcid": "GCID-ONE"},
        ).mock(return_value=httpx.Response(200, json=build_search_payload("https://subtitle.example/1.srt")))

        with TestClient(create_app(settings)) as client:
            response = client.post(
                "/api/v1/subtitles/search",
                json={"gcid": "GCID-ONE", "cid": "CID-ONE", "name": "demo.mkv"},
            )

    body = response.json()
    assert response.status_code == 200
    assert body["matched_by"] == "gcid"
    assert body["confidence"] == "high"
    assert len(body["items"]) == 1
    assert body["items"][0]["download_url"].endswith(f"/api/v1/subtitles/{body['items'][0]['id']}")
    assert gcid_route.call_count == 1


def test_search_fallback_to_name(tmp_path: Path) -> None:
    """GCID 无结果时回退到文件名查询。"""

    settings = build_settings(tmp_path / "data")
    with respx.mock(assert_all_called=True, assert_all_mocked=True) as mock_router:
        mock_router.get(
            "https://api-shoulei-ssl.xunlei.com/oracle/subtitle",
            params={"gcid": "GCID-EMPTY"},
        ).mock(return_value=httpx.Response(200, json={"code": 0, "result": "ok", "data": []}))
        mock_router.get(
            "https://api-shoulei-ssl.xunlei.com/oracle/subtitle",
            params={"name": "demo.mkv"},
        ).mock(return_value=httpx.Response(200, json=build_search_payload("https://subtitle.example/2.srt")))

        with TestClient(create_app(settings)) as client:
            response = client.post(
                "/api/v1/subtitles/search",
                json={"gcid": "GCID-EMPTY", "name": "demo.mkv"},
            )

    body = response.json()
    assert response.status_code == 200
    assert body["matched_by"] == "name"
    assert body["confidence"] == "fallback"
    assert len(body["items"]) == 1


def test_search_result_deduplicates_same_url(tmp_path: Path) -> None:
    """相同上游地址的字幕项应只保留一条。"""

    settings = build_settings(tmp_path / "data")
    duplicated_payload = {
        "code": 0,
        "result": "ok",
        "data": [
            build_search_payload("https://subtitle.example/dup.srt", score=1)["data"][0],
            build_search_payload("https://subtitle.example/dup.srt", score=200)["data"][0],
        ],
    }

    with respx.mock(assert_all_called=True, assert_all_mocked=True) as mock_router:
        mock_router.get(
            "https://api-shoulei-ssl.xunlei.com/oracle/subtitle",
            params={"gcid": "GCID-DUP"},
        ).mock(return_value=httpx.Response(200, json=duplicated_payload))

        with TestClient(create_app(settings)) as client:
            response = client.post("/api/v1/subtitles/search", json={"gcid": "GCID-DUP"})

    body = response.json()
    assert response.status_code == 200
    assert len(body["items"]) == 1
    assert body["items"][0]["score"] == 200


def test_search_cache_prevents_duplicate_upstream_calls(tmp_path: Path) -> None:
    """相同请求命中缓存时不重复访问迅雷。"""

    settings = build_settings(tmp_path / "data")
    with respx.mock(assert_all_mocked=True) as mock_router:
        route = mock_router.get(
            "https://api-shoulei-ssl.xunlei.com/oracle/subtitle",
            params={"gcid": "GCID-CACHE"},
        ).mock(return_value=httpx.Response(200, json=build_search_payload("https://subtitle.example/cache.srt")))

        with TestClient(create_app(settings)) as client:
            first_response = client.post("/api/v1/subtitles/search", json={"gcid": "GCID-CACHE"})
            second_response = client.post("/api/v1/subtitles/search", json={"gcid": "GCID-CACHE"})

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert route.call_count == 1


def test_search_cache_survives_restart(tmp_path: Path) -> None:
    """磁盘缓存应在应用重启后仍可复用。"""

    settings = build_settings(tmp_path / "data")
    with respx.mock(assert_all_called=True, assert_all_mocked=True) as mock_router:
        route = mock_router.get(
            "https://api-shoulei-ssl.xunlei.com/oracle/subtitle",
            params={"gcid": "GCID-RESTART"},
        ).mock(return_value=httpx.Response(200, json=build_search_payload("https://subtitle.example/restart.srt")))

        with TestClient(create_app(settings)) as client:
            first_response = client.post("/api/v1/subtitles/search", json={"gcid": "GCID-RESTART"})

    assert first_response.status_code == 200
    assert route.call_count == 1

    with respx.mock(assert_all_mocked=True):
        with TestClient(create_app(settings)) as client:
            second_response = client.post("/api/v1/subtitles/search", json={"gcid": "GCID-RESTART"})

    assert second_response.status_code == 200


def test_download_proxy_and_cache(tmp_path: Path) -> None:
    """代理下载成功后应缓存字幕内容。"""

    settings = build_settings(tmp_path / "data")
    with respx.mock(assert_all_mocked=True) as mock_router:
        mock_router.get(
            "https://api-shoulei-ssl.xunlei.com/oracle/subtitle",
            params={"gcid": "GCID-DOWNLOAD"},
        ).mock(return_value=httpx.Response(200, json=build_search_payload("https://subtitle.example/download.srt")))
        download_route = mock_router.get("https://subtitle.example/download.srt").mock(
            return_value=httpx.Response(
                200,
                text="1\n00:00:01,000 --> 00:00:02,000\n测试字幕\n",
                headers={"Content-Type": "application/x-subrip; charset=utf-8"},
            )
        )

        with TestClient(create_app(settings)) as client:
            search_response = client.post("/api/v1/subtitles/search", json={"gcid": "GCID-DOWNLOAD"})
            subtitle_id = search_response.json()["items"][0]["id"]

            first_download = client.get(f"/api/v1/subtitles/{subtitle_id}")
            second_download = client.get(f"/api/v1/subtitles/{subtitle_id}")

    assert first_download.status_code == 200
    assert second_download.status_code == 200
    assert first_download.content == second_download.content
    assert download_route.call_count == 1


def test_download_unknown_subtitle_returns_404(tmp_path: Path) -> None:
    """未知字幕项应返回 404。"""

    with TestClient(create_app(build_settings(tmp_path / "data"))) as client:
        response = client.get("/api/v1/subtitles/unknown")

    assert response.status_code == 404


def test_upstream_timeout_returns_504(tmp_path: Path) -> None:
    """上游超时应映射为 504。"""

    settings = build_settings(tmp_path / "data")
    with respx.mock(assert_all_called=True, assert_all_mocked=True) as mock_router:
        mock_router.get(
            "https://api-shoulei-ssl.xunlei.com/oracle/subtitle",
            params={"gcid": "GCID-TIMEOUT"},
        ).mock(side_effect=httpx.ReadTimeout("timeout"))

        with TestClient(create_app(settings)) as client:
            response = client.post("/api/v1/subtitles/search", json={"gcid": "GCID-TIMEOUT"})

    assert response.status_code == 504


def test_upstream_invalid_payload_returns_502(tmp_path: Path) -> None:
    """上游返回失败状态时应映射为 502。"""

    settings = build_settings(tmp_path / "data")
    with respx.mock(assert_all_called=True, assert_all_mocked=True) as mock_router:
        mock_router.get(
            "https://api-shoulei-ssl.xunlei.com/oracle/subtitle",
            params={"gcid": "GCID-FAIL"},
        ).mock(return_value=httpx.Response(200, json={"code": 1, "result": "fail", "data": []}))

        with TestClient(create_app(settings)) as client:
            response = client.post("/api/v1/subtitles/search", json={"gcid": "GCID-FAIL"})

    assert response.status_code == 502
