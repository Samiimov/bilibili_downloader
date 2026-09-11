from unittest.mock import MagicMock

import pytest
import yt_dlp
from yt_dlp.extractor.bilibili import BiliBiliIE, BiliBiliSearchIE
from yt_dlp.networking.exceptions import TransportError
from yt_dlp.utils import ExtractorError

import bilibili_search as app


def test_native_search_paginates_and_returns_titles_without_downloads(monkeypatch):
    ids = ["BV1bXt3e5Eyt", "BV1Ev38zcE2k", "BV1n44y1Q7sc"]
    pages = []

    def search_json(self, url, video_id, **kwargs):
        query = kwargs["query"]
        assert query["keyword"] == "half guard 半防"
        assert query["search_type"] == "video"
        pages.append(query["page"])
        selected = ids[:2] if query["page"] == 1 else ids[2:]
        return {"data": {"result": [
            {"aid": i, "bvid": bvid,
             "title": '<em class="keyword">Half guard</em> 半防 &amp; more',
             "author": "Example uploader"}
            for i, bvid in enumerate(selected)
        ]}}

    no_video_pages = MagicMock(side_effect=AssertionError("Search must not open video pages"))
    no_network = MagicMock(side_effect=AssertionError("Unexpected network request"))
    no_download = MagicMock(side_effect=AssertionError("Search must not download media"))
    monkeypatch.setattr(BiliBiliSearchIE, "_download_json", search_json)
    monkeypatch.setattr(BiliBiliIE, "_real_extract", no_video_pages)
    monkeypatch.setattr(yt_dlp.YoutubeDL, "urlopen", no_network)
    monkeypatch.setattr(yt_dlp.YoutubeDL, "process_info", no_download)

    results = app.search_videos("half guard 半防", limit=3)

    assert pages == [1, 2]
    assert results == [{"title": "Half guard 半防 & more", "uploader": "Example uploader",
                        "url": f"https://www.bilibili.com/video/{bvid}"} for bvid in ids]
    no_download.assert_not_called()
    no_network.assert_not_called()
    no_video_pages.assert_not_called()


def test_search_page_timeout_is_retried(monkeypatch):
    request = MagicMock(side_effect=[
        ExtractorError("The read operation timed out", cause=TransportError("timed out")),
        {"code": 0, "data": {"result": [{"aid": 123, "title": "Found after retry"}]}},
    ])
    monkeypatch.setattr(BiliBiliSearchIE, "_download_json", request)
    monkeypatch.setattr("time.sleep", MagicMock())
    assert app.search_videos("test", limit=1) == [{
        "title": "Found after retry", "url": "https://www.bilibili.com/video/av123",
        "uploader": "",
    }]
    assert request.call_count == 2
    assert [c.kwargs["query"]["page"] for c in request.call_args_list] == [1, 1]


def test_search_timeout_retries_are_bounded(monkeypatch):
    request = MagicMock(side_effect=ExtractorError(
        "The read operation timed out", cause=TransportError("timed out")))
    monkeypatch.setattr(BiliBiliSearchIE, "_download_json", request)
    monkeypatch.setattr("time.sleep", MagicMock())
    with pytest.raises(yt_dlp.utils.DownloadError, match="timed out"):
        app.search_videos("test")
    assert request.call_count == 4


@pytest.mark.parametrize("response,message", [
    ({"code": -412, "message": "Request blocked", "data": None}, "Request blocked"),
    ({"code": 0, "data": None}, "invalid search response"),
])
def test_search_api_errors_are_not_reported_as_no_matches(response, message, monkeypatch):
    request = MagicMock(return_value=response)
    monkeypatch.setattr(BiliBiliSearchIE, "_download_json", request)
    with pytest.raises(yt_dlp.utils.DownloadError, match=message):
        app.search_videos("test")
    assert request.call_count == 1


@pytest.mark.parametrize("query,limit", [(" ", 10), ("test", 0), ("test", -1)])
def test_invalid_search_does_not_make_requests(query, limit, monkeypatch):
    factory = MagicMock()
    monkeypatch.setattr(app.yt_dlp, "YoutubeDL", factory)
    with pytest.raises(ValueError):
        app.search_videos(query, limit)
    factory.assert_not_called()


def test_links_are_canonical_and_duplicates_removed(monkeypatch):
    factory = MagicMock()
    factory.return_value.__enter__.return_value.extract_info.return_value = {
        "entries": [
            {"id": "BV1bXt3e5Eyt_p1", "title": "Title\n半防",
             "webpage_url": "http://www.bilibili.com/video/BV1bXt3e5Eyt/?p=1&track=test"},
            {"id": "BV1bXt3e5Eyt_p2", "title": "Duplicate"},
            None,
        ],
    }
    monkeypatch.setattr(app.yt_dlp, "YoutubeDL", factory)
    assert app.search_videos("test") == [{
        "title": "Title 半防", "url": "https://www.bilibili.com/video/BV1bXt3e5Eyt",
        "uploader": "",
    }]


def test_cli_saves_links_and_prints_titles(tmp_path, monkeypatch, capsys):
    output = tmp_path / "links.txt"
    url = "https://www.bilibili.com/video/BV1bXt3e5Eyt"
    search = MagicMock(return_value=[{"title": "半防", "uploader": "Author", "url": url}])
    monkeypatch.setattr(app, "search_videos", search)
    monkeypatch.setattr("sys.argv", ["bilibili_search.py", "half guard", "-n", "3",
                                    "-o", str(output)])
    app.main()
    search.assert_called_once_with("half guard", 3)
    assert output.read_text(encoding="utf-8") == url + "\n"
    assert "半防" in capsys.readouterr().out


def test_urls_only_and_no_results(monkeypatch, capsys):
    url = "https://www.bilibili.com/video/BV1bXt3e5Eyt"
    search = MagicMock(side_effect=[[{"title": "Title", "uploader": "", "url": url}], []])
    monkeypatch.setattr(app, "search_videos", search)
    monkeypatch.setattr("sys.argv", ["bilibili_search.py", "test", "--urls-only"])
    app.main()
    assert capsys.readouterr().out == url + "\n"
    app.main()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "No matching videos" in captured.err


def test_failed_search_preserves_existing_output(tmp_path, monkeypatch, capsys):
    output = tmp_path / "links.txt"
    output.write_text("Existing links\n")
    monkeypatch.setattr(app, "search_videos", MagicMock(
        side_effect=yt_dlp.utils.DownloadError("HTTP Error 412")))
    monkeypatch.setattr("sys.argv", ["bilibili_search.py", "test", "-o", str(output)])
    with pytest.raises(SystemExit) as result:
        app.main()
    assert result.value.code == 1
    assert output.read_text() == "Existing links\n"
    assert "412" in capsys.readouterr().err
