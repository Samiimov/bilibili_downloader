import argparse
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse

import yt_dlp
from yt_dlp.extractor.bilibili import BiliBiliIE


ALLOWED_HOSTS = {
    "bilibili.com",
    "www.bilibili.com",
    "m.bilibili.com",
    "b23.tv",
}
MAX_URL_REFRESHES = 3


class BiliBiliDownloadIE(BiliBiliIE):
    @classmethod
    def ie_key(cls):
        # Preserve yt-dlp's archive keys and playlist references.
        return "BiliBili"

    @classmethod
    def get_temp_id(cls, url):
        parsed = urlparse(url)
        match = re.fullmatch(r"/video/(BV[a-zA-Z0-9]+)/?", parsed.path)
        parts = dict(parse_qsl(parsed.query)).get("p", "")
        if match and parts.isdigit() and int(parts) > 0:
            return f"{match.group(1)}_p{int(parts)}"
        # A base URL may contain unprocessed parts even when p1 is archived.
        return None

    def extract_formats(self, play_info):
        formats = super().extract_formats(play_info)
        attempt = self.get_param("bilibili_mirror_attempt", 0)
        if not attempt:
            return formats

        mirrors = {}

        def collect(value):
            if isinstance(value, dict):
                primary = value.get("baseUrl") or value.get("base_url") or value.get("url")
                backups = value.get("backupUrl") or value.get("backup_url") or []
                if primary and isinstance(backups, list):
                    urls = list(dict.fromkeys([primary, *[
                        url for url in backups
                        if isinstance(url, str) and url.startswith(("https://", "http://"))
                    ]]))
                    mirrors[primary] = urls[min(attempt, len(urls) - 1)]
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(play_info)
        for fmt in formats:
            # Preserve format IDs so matching video/audio .part files can resume.
            if fmt.get("url") in mirrors:
                fmt["url"] = mirrors[fmt["url"]]
        return formats


def validate_url(url: str):
    parsed = urlparse(url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Only http/https URLs are allowed")

    host = (parsed.hostname or "").lower()

    if host not in ALLOWED_HOSTS and not host.endswith(".bilibili.com"):
        raise ValueError("URL must be a Bilibili URL")


def progress_hook(info):
    status = info.get("status")

    if status == "downloading":
        percent = info.get("_percent_str", "")
        speed = info.get("_speed_str", "")
        eta = info.get("_eta_str", "")

        print(
            f"\rDownloading: {percent} | {speed} | ETA {eta}",
            end="",
            flush=True,
        )

    elif status == "finished":
        print("\nDownload finished. Processing media...")


def record_existing_downloads(ydl, output_path: Path):
    """Recognize completed files created before download history was enabled."""
    for path in output_path.iterdir():
        # Only final media files match: exclude .part, .f30064.mp4 and audio files.
        match = re.search(r"\[(BV[a-zA-Z0-9]+(?:_p\d+)?)\]\.(?:mp4|mkv|webm|flv)$", path.name)
        if not match or not path.is_file() or path.stat().st_size == 0:
            continue
        info = {"id": match.group(1), "ie_key": "BiliBili"}
        if not ydl.in_download_archive(info):
            ydl.record_download_archive(info)


def extract_with_refresh(url: str, options: dict):
    """Refresh media URLs after access/server errors instead of retrying stale URLs."""
    for attempt in range(MAX_URL_REFRESHES + 1):
        try:
            # A new extraction/session gets fresh media URLs. Existing files and
            # matching .part files are reused by yt-dlp on the next attempt.
            with yt_dlp.YoutubeDL({**options, "bilibili_mirror_attempt": attempt}) as ydl:
                ydl.add_info_extractor(BiliBiliDownloadIE())
                if options.get("download_archive"):
                    record_existing_downloads(ydl, Path(options["download_archive"]).parent)
                return ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            status = re.search(r"\bHTTP Error (403|503)\b", str(exc))
            connection_error = re.search(
                r"timed out|Remote end closed connection|Connection reset|Downloaded \d+ bytes, expected",
                str(exc), re.IGNORECASE,
            )
            if not (status or connection_error) or attempt == MAX_URL_REFRESHES:
                raise
            delay = min(5 * 2 ** attempt, 30)
            reason = f"HTTP {status.group(1)}" if status else "Connection failure"
            print(
                f"\n{reason}: refreshing media URLs and trying an available backup server in {delay}s "
                f"({attempt + 1}/{MAX_URL_REFRESHES})..."
            )
            time.sleep(delay)


def download(url: str, output_dir: str = "downloads", max_height: int = 720):
    validate_url(url)
    if max_height <= 0:
        raise ValueError("Maximum height must be positive")

    # A part selector tells yt-dlp to download only that part, even in playlist mode.
    parsed = urlparse(url)
    url = parsed._replace(
        query=urlencode([
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key != "p"
        ]),
    ).geturl()

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    options = {
        # Download every numbered part of each submitted video.
        "noplaylist": False,

        # Cap both separate-video and combined-stream choices; never fall back
        # to 1080p when a lower-resolution format is unavailable.
        "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]",

        # File name
        "outtmpl": str(
            output_path / "%(title).180B [%(id)s].%(ext)s"
        ),

        # Merge separate streams
        "merge_output_format": "mp4",

        # Recover from truncated responses and temporary connection failures.
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "retry_sleep_functions": {
            "http": lambda n: min(2 ** n, 30),
            "fragment": lambda n: min(2 ** n, 30),
        },
        "socket_timeout": 30,
        "http_chunk_size": 10 * 1024 * 1024,

        # Nice console progress
        "progress_hooks": [progress_hook],

        # Preserve Unicode titles
        "restrictfilenames": False,

        # Don't overwrite an existing completed file
        "overwrites": False,

        # yt-dlp records each section only after download and processing succeed.
        "download_archive": str(output_path / "download-archive.txt"),
    }

    info = extract_with_refresh(url, options)

    if info:
        print(f"Title: {info.get('title')}")
        if info.get("_type") == "playlist":
            print("Finished processing all parts; previously completed parts were skipped.")
        else:
            print(f"Uploader: {info.get('uploader')}")
            print(f"Video ID: {info.get('id')}")


def main():
    parser = argparse.ArgumentParser(
        description="Download all parts of a queue of authorized Bilibili videos"
    )

    parser.add_argument(
        "urls", nargs="+",
        help="Bilibili video URLs; all parts of each URL are downloaded in order",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="downloads",
        help="Output directory",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        choices=(360, 480, 720),
        default=720,
        help="Maximum video height in pixels (default: 720)",
    )

    args = parser.parse_args()

    failed = False
    for index, url in enumerate(args.urls, start=1):
        print(f"\n[{index}/{len(args.urls)}] {url}")
        try:
            download(url, args.output, args.max_height)
        except KeyboardInterrupt:
            print("\nDownload interrupted. Rerun with the same output folder to resume.")
            raise SystemExit(130)
        except Exception as exc:
            print(f"\nError downloading {url}: {exc}")
            failed = True

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
