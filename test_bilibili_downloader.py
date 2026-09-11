import io
import re
from unittest.mock import MagicMock, call

import pytest
import yt_dlp
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.networking.common import Response
from yt_dlp.networking.exceptions import HTTPError
from yt_dlp.utils import DownloadError, ExtractorError

import bilibili_downloader as app


URL = "https://www.bilibili.com/video/BV1bXt3e5Eyt"


@pytest.mark.parametrize("status", [403, 503])
def test_refresh_is_bounded(status, monkeypatch):
    factory = MagicMock()
    factory.return_value.__enter__.return_value.extract_info.side_effect = (
        DownloadError(f"ERROR: unable to download video data: HTTP Error {status}")
    )
    sleep = MagicMock()
    monkeypatch.setattr(app.yt_dlp, "YoutubeDL", factory)
    monkeypatch.setattr(app.time, "sleep", sleep)

    with pytest.raises(DownloadError, match=str(status)):
        app.extract_with_refresh(URL, {})

    assert factory.call_count == 4
    assert sleep.call_args_list == [call(5), call(10), call(20)]


def test_unrelated_error_is_not_retried(monkeypatch):
    factory = MagicMock()
    factory.return_value.__enter__.return_value.extract_info.side_effect = (
        DownloadError("Requested format is not available")
    )
    sleep = MagicMock()
    monkeypatch.setattr(app.yt_dlp, "YoutubeDL", factory)
    monkeypatch.setattr(app.time, "sleep", sleep)

    with pytest.raises(DownloadError, match="format"):
        app.extract_with_refresh(URL, {})

    assert factory.call_count == 1
    sleep.assert_not_called()


@pytest.mark.parametrize("max_height", [480, 720])
def test_expired_media_url_is_refreshed_and_partial_file_resumed(
    max_height, tmp_path, monkeypatch,
):
    """Exercise actual yt-dlp extraction, format choice and HTTP file resuming."""
    payload = bytes(range(256)) * 256
    extractions = []
    requests = []
    original_ydl = yt_dlp.YoutubeDL

    class FixtureIE(InfoExtractor):
        _VALID_URL = r"https://www\.bilibili\.com/video/(?P<id>BV\w+)"

        def _real_extract(self, url):
            extractions.append(url)
            return {
                "id": self._match_id(url),
                "title": "Example",
                "formats": [{
                    "format_id": str(height),
                    "height": height,
                    "width": height * 16 // 9,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "ext": "mp4",
                    "url": f"https://media.example.test/{height}?token={len(extractions)}",
                } for height in (360, 480, 720, 1080)],
            }

    def urlopen(request):
        match = re.fullmatch(r"bytes=(\d+)-(\d*)", request.headers["Range"])
        start = int(match[1])
        requests.append((request.url, start))
        if "token=1" in request.url and start:
            raise HTTPError(Response(io.BytesIO(), request.url, {}, status=403))
        # The old URL transfers half the file, then becomes forbidden.
        body = payload[:len(payload) // 2] if "token=1" in request.url else payload[start:]
        return Response(io.BytesIO(body), request.url, {
            "Content-Length": str(len(payload) - start),
            "Content-Range": f"bytes {start}-{len(payload) - 1}/{len(payload)}",
        }, status=206)

    def factory(options):
        ydl = original_ydl({**options, "quiet": True, "noprogress": True}, auto_init=False)
        ydl.add_info_extractor(FixtureIE())
        monkeypatch.setattr(ydl, "urlopen", urlopen)
        return ydl

    monkeypatch.setattr(app.yt_dlp, "YoutubeDL", factory)
    monkeypatch.setattr(app.time, "sleep", MagicMock())
    app.download(URL + "?p=3", str(tmp_path), max_height)

    assert extractions == [URL, URL]
    assert requests == [
        (f"https://media.example.test/{max_height}?token=1", 0),
        (f"https://media.example.test/{max_height}?token=1", len(payload) // 2),
        (f"https://media.example.test/{max_height}?token=2", len(payload) // 2),
    ]
    assert (tmp_path / "Example [BV1bXt3e5Eyt].mp4").read_bytes() == payload
    assert not list(tmp_path.glob("*.part"))


def test_no_fallback_to_1080p(tmp_path, monkeypatch):
    options = {}

    def capture_options(url, settings):
        options.update(settings)

    monkeypatch.setattr(app, "extract_with_refresh", capture_options)
    app.download(URL, str(tmp_path))
    with yt_dlp.YoutubeDL({"format": options["format"], "quiet": True}) as ydl:
        with pytest.raises(ExtractorError, match="Requested format is not available"):
            ydl.process_ie_result({
                "id": "example",
                "extractor": "fixture",
                "title": "Only 1080p available",
                "formats": [{
                    "format_id": "1080",
                    "height": 1080,
                    "vcodec": "h264",
                    "acodec": "aac",
                    "url": "https://media.example.test/1080.mp4",
                }],
            }, download=False)


def test_separate_video_and_audio_respect_quality_cap(tmp_path, monkeypatch):
    options = {}
    monkeypatch.setattr(app, "extract_with_refresh", lambda url, settings: options.update(settings))
    app.download(URL, str(tmp_path))
    with yt_dlp.YoutubeDL({"format": options["format"], "quiet": True}) as ydl:
        info = ydl.process_ie_result({
            "id": "example",
            "title": "Separate streams",
            "extractor": "fixture",
            "formats": [
                {"format_id": "audio", "vcodec": "none", "acodec": "aac",
                 "url": "https://media.example.test/audio.m4a"},
                *[{"format_id": str(height), "height": height,
                   "vcodec": "h264", "acodec": "none",
                   "url": f"https://media.example.test/{height}.mp4"}
                  for height in (480, 720, 1080)],
            ],
        }, download=False)
    assert [fmt["format_id"] for fmt in info["requested_formats"]] == ["720", "audio"]


def test_queue_continues_after_exhausted_refreshes(monkeypatch):
    other_url = "https://www.bilibili.com/video/BV1Ev38zcE2k"
    download = MagicMock(side_effect=[DownloadError("HTTP Error 403"), None])
    monkeypatch.setattr(app, "download", download)
    monkeypatch.setattr("sys.argv", ["bilibili_downloader.py", URL, other_url,
                                    "--max-height", "480"])
    with pytest.raises(SystemExit) as result:
        app.main()

    assert result.value.code == 1
    assert download.call_args_list == [
        call(URL, "downloads", 480), call(other_url, "downloads", 480),
    ]


def test_existing_downloads_exclude_incomplete_files(tmp_path):
    for name in (
        "Complete [BV1bXt3e5Eyt_p1].mp4",
        "Video only [BV1bXt3e5Eyt_p2].f30064.mp4",
        "Audio only [BV1bXt3e5Eyt_p3].f30280.m4a",
        "Partial [BV1bXt3e5Eyt_p4].mp4.part",
        "Metadata [BV1bXt3e5Eyt_p5].info.json",
    ):
        (tmp_path / name).write_bytes(b"existing data")
    (tmp_path / "Empty [BV1bXt3e5Eyt_p6].mp4").touch()
    archive = tmp_path / "download-archive.txt"
    with yt_dlp.YoutubeDL({"download_archive": str(archive)}) as ydl:
        app.record_existing_downloads(ydl, tmp_path)
        app.record_existing_downloads(ydl, tmp_path)
    assert archive.read_text().splitlines() == ["bilibili BV1bXt3e5Eyt_p1"]


def test_playlist_skips_completed_parts_across_runs(tmp_path, monkeypatch):
    """Migrate four old downloads, fail later, and resume only unfinished parts."""
    original_ydl = yt_dlp.YoutubeDL
    payload = b"fixture video data"
    requests = []
    extracted_parts = []
    fail_part_six = True

    for part in range(1, 5):
        (tmp_path / f"Old title [BV1bXt3e5Eyt_p{part}].mp4").write_bytes(payload)

    class FixtureIE(app.BiliBiliDownloadIE):
        _VALID_URL = r"https://www\.bilibili\.com/video/(?P<id>BV\w+)(?:\?p=(?P<part>\d+))?"

        @classmethod
        def ie_key(cls):
            return "BiliBili"

        def _real_extract(self, url):
            match = self._match_valid_url(url)
            if not match["part"]:
                return self.playlist_result([
                    self.url_result(f"{URL}?p={part}", ie=self.ie_key())
                    for part in range(1, 9)
                ], playlist_id=match["id"], playlist_title="Eight sections")
            part = int(match["part"])
            extracted_parts.append(part)
            return {
                "id": f"{match['id']}_p{part}",
                "title": "New title",
                "height": 480,
                "vcodec": "h264",
                "acodec": "aac",
                "ext": "mp4",
                "url": f"https://media.example.test/{part}.mp4",
            }

    def urlopen(request):
        part = int(request.url.rsplit("/", 1)[-1].split(".")[0])
        requests.append(part)
        if fail_part_six and part == 6:
            raise HTTPError(Response(io.BytesIO(), request.url, {}, status=404))
        return Response(io.BytesIO(payload), request.url, {
            "Content-Length": str(len(payload)),
            "Content-Range": f"bytes 0-{len(payload) - 1}/{len(payload)}",
        }, status=206)

    def factory(options):
        ydl = original_ydl({**options, "quiet": True, "noprogress": True}, auto_init=False)
        ydl.add_info_extractor(FixtureIE())
        monkeypatch.setattr(ydl, "urlopen", urlopen)
        return ydl

    monkeypatch.setattr(app.yt_dlp, "YoutubeDL", factory)
    monkeypatch.setattr(app, "BiliBiliDownloadIE", FixtureIE)
    with pytest.raises(DownloadError, match="404"):
        app.download(URL, str(tmp_path))
    assert requests == [5, 6]
    assert extracted_parts == [5, 6]
    archive = tmp_path / "download-archive.txt"
    assert set(archive.read_text().splitlines()) == {
        f"bilibili BV1bXt3e5Eyt_p{part}" for part in range(1, 6)
    }

    fail_part_six = False
    requests.clear()
    extracted_parts.clear()
    app.download(URL, str(tmp_path), max_height=480)
    assert requests == [6, 7, 8]
    assert extracted_parts == [6, 7, 8]
    assert set(archive.read_text().splitlines()) == {
        f"bilibili BV1bXt3e5Eyt_p{part}" for part in range(1, 9)
    }
    requests.clear()
    extracted_parts.clear()
    app.download(URL, str(tmp_path))
    assert requests == []
    assert extracted_parts == []


@pytest.mark.parametrize("message", [
    "Remote end closed connection without response. Giving up after 3 retries",
    "The read operation timed out",
    "Connection reset by peer",
])
def test_transport_failures_refresh_media_urls(message, monkeypatch):
    factory = MagicMock()
    factory.return_value.__enter__.return_value.extract_info.side_effect = [
        DownloadError(message), {"id": "done"},
    ]
    monkeypatch.setattr(app.yt_dlp, "YoutubeDL", factory)
    monkeypatch.setattr(app.time, "sleep", MagicMock())
    assert app.extract_with_refresh(URL, {}) == {"id": "done"}
    assert [c.args[0]["bilibili_mirror_attempt"] for c in factory.call_args_list] == [0, 1]


@pytest.mark.parametrize("backup_key", ["backupUrl", "backup_url"])
def test_audio_resumes_from_backup_after_primary_server_fails(backup_key, tmp_path, monkeypatch):
    original_ydl = yt_dlp.YoutubeDL
    primary = "https://primary.example.test/audio.m4a"
    backup = "https://backup.example.test/audio.m4a"
    payload = bytes(range(256)) * 256
    requests = []

    class FixtureIE(app.BiliBiliDownloadIE):
        def _real_extract(self, url):
            return {
                "id": "BV1bXt3e5Eyt_p6", "title": "Audio",
                "formats": self.extract_formats({"dash": {"audio": [{
                    "id": 30280, "baseUrl": primary, backup_key: [backup],
                    "mimeType": "audio/mp4", "codecs": "mp4a.40.2", "bandwidth": 128000,
                }]}}),
            }

    def urlopen(request):
        start = int(request.headers["Range"].split("=")[1].split("-")[0])
        requests.append((request.url, start))
        if request.url == primary and start:
            raise HTTPError(Response(io.BytesIO(), request.url, {}, status=503))
        body = payload[:len(payload) // 2] if request.url == primary else payload[start:]
        return Response(io.BytesIO(body), request.url, {
            "Content-Length": str(len(payload) - start),
            "Content-Range": f"bytes {start}-{len(payload) - 1}/{len(payload)}",
        }, status=206)

    def factory(options):
        ydl = original_ydl({**options, "quiet": True, "noprogress": True}, auto_init=False)
        monkeypatch.setattr(ydl, "urlopen", urlopen)
        return ydl

    monkeypatch.setattr(app.yt_dlp, "YoutubeDL", factory)
    monkeypatch.setattr(app, "BiliBiliDownloadIE", FixtureIE)
    monkeypatch.setattr(app.time, "sleep", MagicMock())
    info = app.extract_with_refresh(URL + "?p=6", {
        "format": "ba", "outtmpl": str(tmp_path / "%(id)s.f%(format_id)s.%(ext)s"),
        "retries": 3, "http_chunk_size": 1024 * 1024, "continuedl": True,
    })
    assert info["format_id"] == "30280"
    assert requests[:-1] == [(primary, 0)] + [(primary, len(payload) // 2)] * 4
    assert requests[-1][0] == backup
    # Resume from persisted bytes; a failed connection may leave a buffered tail.
    assert 0 < requests[-1][1] <= len(payload) // 2
    assert (tmp_path / "BV1bXt3e5Eyt_p6.f30280.m4a").read_bytes() == payload


def test_interrupt_exits_cleanly(monkeypatch, capsys):
    monkeypatch.setattr(app, "download", MagicMock(side_effect=KeyboardInterrupt))
    monkeypatch.setattr("sys.argv", ["bilibili_downloader.py", URL])
    with pytest.raises(SystemExit) as result:
        app.main()
    assert result.value.code == 130
    assert "resume" in capsys.readouterr().out
