"""Keep newblog catch-up VODs immediately before the first GCCX VOD.

newblog/sync_tv.py owns the replay content; the separate KICK updater owns VOD5.
Callers must lift the newblog block before replacing the VOD5 catalog, then
reinsert it so hourly rebuilds never lose or reorder the replays.
"""
from __future__ import annotations

import re

NEWBLOG_START = "# === NEWBLOG_VOD_START ==="
NEWBLOG_END = "# === NEWBLOG_VOD_END ==="
VOD5_START = "# === VOD5_CATALOG_START ==="
VOD5_END = "# === VOD5_CATALOG_END ==="
BLOCK = re.compile(
    r"(?m)^" + re.escape(NEWBLOG_START) + r"\r?\n.*?^"
    + re.escape(NEWBLOG_END) + r"(?:\r?\n|$)", re.S,
)
GCCX_ROW = re.compile(r'(?m)^#EXTINF:[^\n]*\btvg-id="kick\.(?:gccx|gmcx)[^"\n]*"')


def pop_newblog_vod(text: str) -> tuple[str, str]:
    """Extract one managed replay block without changing unrelated entries."""
    hits = list(BLOCK.finditer(text))
    if not hits:
        return "", text
    if len(hits) != 1:
        raise ValueError("Duplicate NEWBLOG_VOD sections; refusing to reorder")
    m = hits[0]
    block = m.group(0).strip("\r\n")
    before = text[:m.start()].rstrip("\r\n")
    after = text[m.end():].lstrip("\r\n")
    if before and after:
        rest = before + "\n\n" + after
    else:
        rest = before + ("\n" if before else "") + after
    return block, rest


def insert_newblog_vod(text: str, block: str) -> str:
    """Insert before the first GCCX VOD, falling back to the VOD5 start."""
    if not block:
        return text
    start = text.find(VOD5_START)
    end = text.find(VOD5_END, start + len(VOD5_START)) if start >= 0 else -1
    if start >= 0 and end >= 0:
        match = GCCX_ROW.search(text, start + len(VOD5_START), end)
        at = match.start() if match else start
    else:
        at = len(text)
    front = text[:at].rstrip("\r\n")
    back = text[at:].lstrip("\r\n")
    if front and back:
        result = front + "\n\n" + block + "\n\n" + back
    elif front:
        result = front + "\n\n" + block
    elif back:
        result = block + "\n\n" + back
    else:
        result = block
    return result.rstrip("\n") + "\n"


def position_newblog_vod(text: str) -> str:
    """Idempotently relocate existing newblog replays beside GCCX VOD."""
    block, rest = pop_newblog_vod(text)
    return insert_newblog_vod(rest, block)
