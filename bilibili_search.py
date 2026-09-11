"""Search Bilibili for video titles and links without downloading media."""

import argparse
import itertools
import re
import sys
import uuid
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.extractor.bilibili import BiliBiliSearchIE
from yt_dlp.networking.exceptions import HTTPError, TransportError
from yt_dlp.utils import ExtractorError, clean_html


class BiliBiliMetadataSearchIE(BiliBiliSearchIE):
    """Keep search API metadata that the upstream search extractor discards."""

    def _search_results(self, query):
        if not self._get_cookies("https://api.bilibili.com").get("buvid3"):
            self._set_cookie(".bilibili.com", "buvid3", f"{uuid.uuid4()}infoc")
        for page in itertools.count(1):
            for retry in self.RetryManager():
                try:
                    response = self._download_json(
                        "https://api.bilibili.com/x/web-interface/search/type", query,
                        note=f"Searching page {page}",
                        query={"keyword": query, "search_type": "video", "page": page},
                    )
                except ExtractorError as exc:
                    cause = exc.cause
                    if isinstance(cause, TransportError) or (
                        isinstance(cause, HTTPError) and (cause.status == 429 or cause.status >= 500)
                    ):
                        retry.error = exc
                        continue
                    raise
                break

            if response.get("code", 0) != 0:
                raise ExtractorError(
                    f"Bilibili search failed ({response['code']}): {response.get('message', '')}",
                    expected=True,
                )
            data = response.get("data")
            if not isinstance(data, dict):
                raise ExtractorError("Bilibili returned an invalid search response", expected=True)
            videos = data.get("result") or []
            if not videos:
                return
            for video in videos:
                video_id = video.get("bvid") or f"av{video['aid']}"
                yield self.url_result(
                    f"https://www.bilibili.com/video/{video_id}", "BiliBili", video_id,
                    clean_html(video.get("title")) or video_id,
                    uploader=video.get("author") or "",
                )


def search_videos(query: str, limit: int = 10) -> list[dict[str, str]]:
    query = query.strip()
    if not query:
        raise ValueError("Search query must not be empty")
    if limit < 1:
        raise ValueError("Result limit must be at least 1")

    options = {
        "quiet": True,
        "skip_download": True,
        # Titles and uploaders come from search results; never open video pages.
        "extract_flat": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "extractor_retries": 3,
        "retry_sleep_functions": {"extractor": lambda n: min(2 ** n, 10)},
    }
    with yt_dlp.YoutubeDL(options) as ydl:
        ydl.add_info_extractor(BiliBiliMetadataSearchIE())
        info = ydl.extract_info(f"bilisearch{limit}:{query}", download=False,
                                ie_key=BiliBiliMetadataSearchIE.ie_key())

    if info is None:
        raise RuntimeError("Bilibili did not return search results")

    results = []
    seen = set()
    for entry in info.get("entries") or []:
        if not entry:
            continue
        webpage_url = entry.get("webpage_url") or entry.get("original_url") or entry.get("url") or ""
        match = re.fullmatch(r"/video/(BV[a-zA-Z0-9]+|av\d+)/?", urlparse(webpage_url).path)
        video_id = match.group(1) if match else str(entry.get("id", "")).split("_p")[0]
        if not re.fullmatch(r"BV[a-zA-Z0-9]+|av\d+", video_id):
            raise ValueError("A search result did not contain a Bilibili video link")
        url = f"https://www.bilibili.com/video/{video_id}"
        if url in seen:
            continue
        seen.add(url)
        results.append({
            "title": " ".join((entry.get("title") or video_id).split()),
            "url": url,
            "uploader": entry.get("uploader") or "",
        })
    return results


def main():
    parser = argparse.ArgumentParser(description="Find Bilibili videos by search phrase")
    parser.add_argument("query", help="Search phrase (quote phrases containing spaces)")
    parser.add_argument("-n", "--limit", type=int, default=10,
                        help="Maximum search results to retrieve (default: 10)")
    parser.add_argument("--urls-only", action="store_true",
                        help="Print only video links, one per line")
    parser.add_argument("-o", "--output", type=Path,
                        help="Save links to a UTF-8 text file, one per line (overwrites file)")
    args = parser.parse_args()
    if not args.query.strip():
        parser.error("Search query must not be empty")
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    try:
        results = search_videos(args.query, args.limit)
        if args.output:
            args.output.write_text("".join(f"{result['url']}\n" for result in results),
                                   encoding="utf-8")
        if not results:
            print("No matching videos found.", file=sys.stderr)
        for index, result in enumerate(results, start=1):
            if args.urls_only:
                print(result["url"])
            else:
                print(f"{index}. {result['title']}")
                if result["uploader"]:
                    print(f"   Uploader: {result['uploader']}")
                print(f"   {result['url']}")
    except (yt_dlp.utils.DownloadError, ValueError, RuntimeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
