"""Evidence after a run: the video is cut to BROWSER_MAX_SECONDS before upload, and local files are deleted afterwards.

The recording runs for the whole life of the browser context, which includes the wait for the user's yes (up to the approval
TTL). A video longer than the run's time budget is trimmed to its first `max_seconds`; the proposal screenshot, the final
screenshot and the receipt PDF cover what happens later. If the video cannot be trimmed (no ffmpeg, ffmpeg fails) it is NOT
uploaded: an untrimmed recording is never stored.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import structlog

log = structlog.get_logger("dialogbot.browser_worker")


def ffmpeg_path() -> str | None:
    return os.environ.get("BROWSER_FFMPEG") or shutil.which("ffmpeg")


def cap_video(src: Path | None, dst: Path, max_seconds: int) -> Path | None:
    """`src` cut to at most `max_seconds`, written to `dst`; None if that could not be done."""
    if src is None or not Path(src).exists():
        return None
    exe = ffmpeg_path()
    if exe is None:
        log.warning("browser.video_not_uploaded", reason="ffmpeg missing")
        return None
    try:
        subprocess.run([exe, "-y", "-v", "error", "-i", str(src), "-t", str(max_seconds), "-c", "copy", str(dst)],
                       check=True, capture_output=True, timeout=120)
    except (subprocess.SubprocessError, OSError) as e:
        log.warning("browser.video_not_uploaded", reason=type(e).__name__)
        return None
    return dst if dst.exists() and dst.stat().st_size > 0 else None
