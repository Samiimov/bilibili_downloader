# Bilibili Downloader

A command-line tool that downloads all numbered parts of one or more Bilibili
videos, using yt-dlp. It remembers completed parts so you can rerun a link after
an interruption without downloading those parts again.

Use `bilibili_search.py` to find videos by a search phrase and list their titles,
uploaders, and links before choosing what to download.

## Table of contents

- [How setup and downloading work](#how-setup-and-downloading-work)
- [Linux](#linux)
  - [Install Python and FFmpeg](#install-python-and-ffmpeg)
  - [With Poetry](#option-a-with-poetry)
  - [Without Poetry](#option-b-without-poetry)
- [Windows](#windows)
  - [Install Python and FFmpeg](#install-python-and-ffmpeg-1)
  - [With Poetry](#option-a-with-poetry-1)
  - [Without Poetry](#option-b-without-poetry-1)
- [Searching for videos](#searching-for-videos)
- [Running the downloader](#running-the-downloader)
  - [Queue multiple links](#queue-multiple-links)
  - [Choose quality and destination](#choose-quality-and-destination)
  - [Resume an interrupted queue](#resume-an-interrupted-queue)
- [Error recovery and troubleshooting](#error-recovery-and-troubleshooting)
- [Updating yt-dlp](#updating-yt-dlp)
- [Development checks](#development-checks)

## How setup and downloading work

There is no separate installer or desktop application. Setup installs Python,
FFmpeg, and the Python dependencies; you then run `bilibili_downloader.py` from
the project folder.

- **Python:** This project requires Python 3.11 or newer, below Python 4.
- **yt-dlp:** Finds the video parts and downloads the media streams.
- **FFmpeg and ffprobe:** Must be available on your system's `PATH`. FFmpeg merges
  each part's separate video and audio streams. Installing a Python package named
  `ffmpeg` does not install these executables.
- **Poetry (optional):** Manages a Python environment and installs the dependency
  versions recorded in `poetry.lock`. The pip instructions below install yt-dlp
  directly into a local `.venv` and do not use the lock file.

The project uses Poetry's `package-mode = false`: it runs as a script and does
not install a `bili-downloader` command. You do not need to run `pip install .`.

Choose the instructions for your operating system and either Poetry or pip.
Download or clone the project first, keeping `bilibili_downloader.py`, `bilibili_search.py`,
`pyproject.toml`, and `poetry.lock` together. Replace the example project paths
below with your actual folder.

## Linux

### Install Python and FFmpeg

On Ubuntu or Debian:

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip ffmpeg
python3 --version
ffmpeg -version
ffprobe -version
```

Check that Python is at least 3.11. If your distribution ships an older Python,
install a supported version before continuing. On other Linux distributions,
install the equivalent packages using your package manager.

### Option A: With Poetry

Install Poetry through pipx, which keeps Poetry in its own environment. This is
one of the methods in the [Poetry installation documentation](https://python-poetry.org/docs/#installation).

```bash
sudo apt install pipx
pipx ensurepath
```

Close and reopen your terminal, then run:

```bash
pipx install poetry
poetry --version
cd /path/to/bilibili_downloader
poetry env use python3
poetry install --only main
```

Run the downloader from the project folder:

```bash
poetry run python bilibili_downloader.py "https://www.bilibili.com/video/BV1bXt3e5Eyt"
```

### Option B: Without Poetry

Create a virtual environment and install yt-dlp:

```bash
cd /path/to/bilibili_downloader
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install yt-dlp
```

Run using that environment's Python:

```bash
.venv/bin/python bilibili_downloader.py "https://www.bilibili.com/video/BV1bXt3e5Eyt"
```

The commands use the virtual environment directly, so activation is unnecessary.
See Python's [virtual environment documentation](https://docs.python.org/3/library/venv.html)
for more about how this works.

## Windows

These commands use **PowerShell**.

### Install Python and FFmpeg

If you have Windows Package Manager (`winget`), install Python 3.12 and FFmpeg:

```powershell
winget install --exact --id Python.Python.3.12
winget install --exact --id Gyan.FFmpeg
```

Close and reopen PowerShell so it picks up the updated `PATH`, then check:

```powershell
py -3.12 --version
ffmpeg -version
ffprobe -version
```

If `winget` is unavailable, install Python from the
[Python Windows downloads page](https://www.python.org/downloads/windows/).
Install a Windows FFmpeg build linked from the
[FFmpeg downloads page](https://ffmpeg.org/download.html), extract it, and add
the folder containing `ffmpeg.exe` and `ffprobe.exe` to your user `Path`
environment variable. Reopen PowerShell afterward. The
[Gyan FFmpeg build provider](https://www.gyan.dev/ffmpeg/builds/) also documents
its package-manager installation options.

The examples below use Python 3.12. If you already have a different supported
version installed, substitute its version for `3.12` in the commands.

### Option A: With Poetry

Install pipx and Poetry:

```powershell
py -3.12 -m pip install --user pipx
py -3.12 -m pipx ensurepath
py -3.12 -m pipx install poetry
```

Close and reopen PowerShell, then install the project's dependencies:

```powershell
poetry --version
cd "C:\path\to\bilibili_downloader"
poetry env use 3.12
poetry install --only main
```

Run the downloader:

```powershell
poetry run python bilibili_downloader.py "https://www.bilibili.com/video/BV1bXt3e5Eyt"
```

### Option B: Without Poetry

Create a virtual environment and install yt-dlp:

```powershell
cd "C:\path\to\bilibili_downloader"
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install yt-dlp
```

Run using that environment's Python:

```powershell
.\.venv\Scripts\python.exe bilibili_downloader.py "https://www.bilibili.com/video/BV1bXt3e5Eyt"
```

These commands do not run `Activate.ps1`, so no PowerShell execution-policy change
is needed to activate the environment.

## Searching for videos

The search script uses the same Python environment and yt-dlp dependency as the
downloader. Searching does not require FFmpeg and does not download media or
modify the download history.

With Poetry, on either Linux or Windows:

```text
poetry run python bilibili_search.py "Peppa the pig" --limit 10
```

Without Poetry, on Linux:

```bash
.venv/bin/python bilibili_search.py "Peppa the pig" --limit 10
```

Without Poetry, on Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe bilibili_search.py "Peppa the pig" --limit 10
```

Chinese search phrases work too. Quote phrases containing spaces. Results follow
Bilibili's search order. Titles, uploaders, and links come directly from the
search API, without opening each video's detail page or expanding its numbered
parts. Search highlighting is removed from titles. The script extends
[yt-dlp's Bilibili search extractor](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/bilibili.py)
to preserve this metadata.

| Argument | Meaning | Default |
| --- | --- | --- |
| `query` | Search phrase | Required |
| `-n`, `--limit` | Maximum search results to retrieve, at least 1 | `10` |
| `--urls-only` | Print just the video links, one per line | Show titles and uploaders too |
| `-o`, `--output` | Save links to a UTF-8 text file, overwriting it | No file |

The output file's parent folder must already exist. Duplicate links are removed,
so there may be fewer distinct results than the requested limit. No matches is
a successful search with an empty result list. Request or file errors exit with
status `1`. Each search page has a 30-second timeout and up to three retries with
increasing delays for transport failures, HTTP 429, or server errors. Bilibili
can still reject search requests; persistent errors are reported instead of
being treated as an empty search.

Save links for review:

```text
poetry run python bilibili_search.py "Peppa Pig" -n 20 -o links.txt
```

After reviewing `links.txt`, pass its links to the downloader. In Linux Bash:

```bash
mapfile -t links < links.txt
if [ "${#links[@]}" -gt 0 ]; then
    poetry run python bilibili_downloader.py "${links[@]}"
fi
```

In Windows PowerShell:

```powershell
$videoLinks = @(Get-Content -Encoding UTF8 .\links.txt | Where-Object { $_.Trim() })
if ($videoLinks.Count -gt 0) {
    poetry run python bilibili_downloader.py @videoLinks
}
```

For pip installations, substitute the appropriate `.venv` Python command shown
above for `poetry run python`. The downloader downloads every numbered part of
each selected video, skipping completed parts using its download history.

## Running the downloader

The examples in this section use Poetry and work in both Bash and PowerShell.
For a pip installation, replace `poetry run python` with `.venv/bin/python` on
Linux or `.\.venv\Scripts\python.exe` on Windows.

### Queue multiple links

```text
poetry run python bilibili_downloader.py "https://www.bilibili.com/video/BV1bXt3e5Eyt" "https://www.bilibili.com/video/BV1Ev38zcE2k"
```

Links are processed in the supplied order. Each link expands into all numbered
parts. A link with `?p=3` also downloads all parts: the script removes the part
selector before passing the link to yt-dlp. Quote URLs, especially those with
`&` in their query string.

Each part is saved as its own video. FFmpeg merges the audio and video for that
part; the script does not concatenate all parts into one long video.

### Choose quality and destination

```text
poetry run python bilibili_downloader.py --max-height 480 -o "my downloads" "https://www.bilibili.com/video/BV1bXt3e5Eyt"
```

| Argument | Meaning | Default |
| --- | --- | --- |
| `urls` | One or more Bilibili links | Required |
| `-o`, `--output` | Destination folder, created if needed | `downloads` |
| `--max-height` | Maximum video height: `360`, `480`, or `720` | `720` |
| `-h`, `--help` | Show usage | — |

The script chooses an available format at or below the height limit. It does not
fall back to 1080p or resize a higher-resolution video. If no suitable format is
available, it reports an error.

Relative output paths are resolved from your terminal's current folder. Run
from the same project folder each time, or use an absolute output path.

### Resume an interrupted queue

Run the same command again with the **same output folder**.

- `download-archive.txt` in that folder records successfully completed sections.
  For an eight-part link with four recorded parts, only the remaining four need
  downloading. Archived numbered BV parts are skipped before fetching their
  detail pages; the base video page is still fetched to discover the part list.
- Existing nonempty final files with names such as `Title [BV1bXt3e5Eyt_p1].mp4`
  are imported into the history. Supported final extensions are `.mp4`, `.mkv`,
  `.webm`, and `.flv`. Recognition uses the filename, not a media-integrity check.
- `.part` files and separate streams such as `.f30064.mp4` and `.f30280.m4a`
  are not considered completed sections. Keep them so yt-dlp can reuse or resume
  compatible files. Changing the selected format may require a new stream download.
- Completed sections remain skipped even if you change the quality setting.
  History is not cleared when you delete a video. To intentionally download a
  fresh copy or a different quality, use a new output folder.

## Error recovery and troubleshooting

HTTP transfers and fragments have up to three retries with increasing delays, a
30-second socket timeout, and 10 MiB HTTP chunks. Persistent 403/503 errors,
timeouts, closed/reset connections, or truncated transfers trigger up to three
fresh extractions of the submitted link, with waits of 5, 10, and 20 seconds.
Each fresh attempt selects a backup media URL supplied by Bilibili when one is
available. Format IDs are preserved so compatible partial streams can resume.
Completed sections are skipped during those attempts too. These retries cannot
guarantee recovery when all available servers fail.

Video and audio are downloaded separately. Lowering `--max-height` reduces video
resolution but does not change the selected audio stream. A successful video
download followed by an audio error leaves that section unfinished.

Press Ctrl+C to stop with exit status `130`. The script keeps partial files and
prints a reminder to rerun with the same output folder to resume.

If a link still fails, the script proceeds to the next queued link and exits
with status `1` when the queue finishes. It does not automatically continue to
later sections of that failed link after exhausting recovery; rerun the link
to attempt its remaining sections.

| Symptom | What to check |
| --- | --- |
| `ffmpeg` or `ffprobe` not found | Install the executables, add their folder to `PATH`, and reopen the terminal. |
| `No module named yt_dlp` | Use `poetry run python` or the `.venv` Python from your installation method. |
| `poetry` not found | Run pipx's `ensurepath` command and reopen the terminal. |
| Python version rejected | Check that the selected interpreter is Python 3.11 or newer, below 4. |
| 1080p premium-format notice | This can appear while yt-dlp lists unavailable formats. The script still selects at most your configured height. |
| Timeouts, incomplete transfers, or 503 errors | Allow retries to finish; rerun with the same output folder if needed. |
| Persistent 403 errors | Refreshing media URLs cannot resolve every server or account restriction. Check whether the link plays in your browser. |

The script currently does not expose yt-dlp's `--cookies` or
`--cookies-from-browser` options; passing those flags to this script will fail.

## Updating yt-dlp

With Poetry, from the project folder:

```text
poetry update yt-dlp
```

This updates the selected dependency and the lock file. To keep using the
repository's locked versions instead, use `poetry install --only main`.

Without Poetry, on Linux:

```bash
.venv/bin/python -m pip install --upgrade yt-dlp
```

Without Poetry, on Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade yt-dlp
```

## Development checks

With Poetry, install the development dependencies and run:

```text
poetry install
poetry run pytest -q
poetry run ruff check bilibili_downloader.py bilibili_search.py test_bilibili_downloader.py test_bilibili_search.py
```

Without Poetry, install the test tools into your existing environment. On Linux:

```bash
.venv/bin/python -m pip install "pytest>=8,<9" "ruff>=0.13,<0.14"
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check bilibili_downloader.py bilibili_search.py test_bilibili_downloader.py test_bilibili_search.py
```

On Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install "pytest>=8,<9" "ruff>=0.13,<0.14"
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check bilibili_downloader.py bilibili_search.py test_bilibili_downloader.py test_bilibili_search.py
```

Tests use simulated responses and do not download live Bilibili videos.
