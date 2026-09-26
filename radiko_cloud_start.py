#!/usr/bin/env python3
from __future__ import annotations

import base64
import fcntl
import html as html_lib
import json
import os
import re
import struct
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

os.environ.setdefault("RADIKO_PROXY_HOST", "0.0.0.0")
os.environ.setdefault("RADIKO_PROXY_PORT", os.environ.get("PORT", "10000"))

import radiko_proxy_core as core

RADIO_TV_IMPORT_ERROR = None
try:
    import radio_tv_filemux as radio_tv
except Exception as e:
    radio_tv = None
    RADIO_TV_IMPORT_ERROR = f"{type(e).__name__}: {e}"
    print(f"[radio-tv] disabled at startup: {RADIO_TV_IMPORT_ERROR}", flush=True)

def cloud_auth(force: bool = False):
    now = time.time()
    with core.LOCK:
        if not force and core.STATE["token"] and now - core.STATE["token_time"] < 2100:
            return core.STATE["token"], core.STATE["detected_area"]
    session = core.premium_login(force=force)
    try:
        with core.open_url(core.API + "/v2/api/auth1", core.BASE_HEADERS, timeout=30) as r:
            token = r.headers.get("X-Radiko-AuthToken")
            off = r.headers.get("X-Radiko-KeyOffset")
            length = r.headers.get("X-Radiko-KeyLength")
    except Exception as e:
        raise RuntimeError(f"auth1 failed: {type(e).__name__}: {e}") from e
    if not token or off is None or length is None:
        raise RuntimeError("auth1 failed: required response headers are missing")
    off = int(off)
    length = int(length)
    part = core.AUTH_KEY[off : off + length]
    if len(part) != length:
        raise RuntimeError("auth1 failed: partial-key range is invalid")
    headers = dict(core.BASE_HEADERS)
    headers.update({"X-Radiko-AuthToken": token,"X-Radiko-PartialKey": base64.b64encode(part).decode(),"X-Radiko-Session": session})
    try:
        with core.open_url(core.API + "/v2/api/auth2", headers, timeout=30) as r:
            body = r.read().decode("utf-8", "replace").strip()
    except Exception as e:
        raise RuntimeError(f"auth2 failed: {type(e).__name__}: {e}") from e
    if not body or body == "OUT":
        raise RuntimeError("auth2 returned OUT after X-Radiko-Session; cloud egress is likely outside Radiko Japan service area")
    detected = body.split(",", 1)[0].strip()
    if not re.fullmatch(r"JP\d{1,2}", detected):
        raise RuntimeError(f"auth2 returned invalid area: {body[:80]}")
    with core.LOCK:
        core.STATE["token"] = token
        core.STATE["token_time"] = now
        core.STATE["detected_area"] = detected
    print(f"[radiko] cloud auth OK detected={detected} mode=premium-session-header", flush=True)
    return token, detected


def tun_capability_report() -> str:
    path = "/dev/net/tun"
    lines = [f"tun_exists={os.path.exists(path)}"]
    if not os.path.exists(path):
        lines.extend(["tun_create=false", "reason=no_/dev/net/tun"])
        return "\n".join(lines) + "\n"
    fd = None
    try:
        fd = os.open(path, os.O_RDWR)
        lines.append("tun_open=true")
        result = fcntl.ioctl(fd, 0x400454CA, struct.pack("16sH", b"rgate%d", 0x0001 | 0x1000))
        lines.extend(["tun_create=true", f"interface={result[:16].split(b'\x00',1)[0].decode('ascii','replace')}"])
    except Exception as e:
        lines.extend(["tun_create=false", f"reason={type(e).__name__}:{e}"])
    finally:
        if fd is not None:
            os.close(fd)
    return "\n".join(lines) + "\n"



GCH_JST = timezone(timedelta(hours=9))
GCH_SITEMAP = "https://www.greenchannel.jp/sitemap.html"
GCH_LOCAL_PAGE = "https://www.greenchannel.jp/program/racing-chihoukeiba-chukei.html"
GCH_VERIFIED_STATUS = "https://raw.githubusercontent.com/ajiousama/himitsu/main/verified_daily_status.json"
GCH_CACHE = {"at": 0.0, "value": None}


def _gch_fetch_text(url: str, timeout: int = 12) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; FreeWiFi-GCH-Status/1.0)",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        charset = r.headers.get_content_charset() or "utf-8"
        return r.read().decode(charset, "replace")


def _gch_visible_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(?:script|style)\b.*?</(?:script|style)>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    return " ".join(html_lib.unescape(raw).split())


def _gch_page_title(raw: str) -> str:
    m = re.search(r"(?is)<h[12][^>]*>(.*?)</h[12]>", raw)
    return _gch_visible_text(m.group(1)) if m else ""


def _gch_today_in_broadcast_time(text: str, now: datetime) -> bool:
    m = re.search(r"放送時間\s*(.*?)(?:出演者|番組内容|新着情報|アクセスランキング)", text, re.S)
    segment = m.group(1) if m else ""
    if not segment:
        return False
    for month, day in re.findall(r"(\d{1,2})月\s*(\d{1,2})日", segment):
        if int(month) == now.month and int(day) == now.day:
            return True
    return False


def _gch_special_broadcasts(now: datetime) -> tuple[list[dict], list[str]]:
    broadcasts = []
    errors = []
    pages = [(GCH_LOCAL_PAGE, "グリーンチャンネル地方競馬中継")]

    try:
        sitemap = _gch_fetch_text(GCH_SITEMAP)
        for href, inner in re.findall(r'(?is)<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', sitemap):
            title = _gch_visible_text(inner)
            if "中継" not in title:
                continue
            if "中央競馬全レース中継" in title or "中央競馬パドック中継" in title:
                continue
            url = urllib.parse.urljoin(GCH_SITEMAP, href)
            if "greenchannel.jp/program/" not in url:
                continue
            pages.append((url, title))
    except Exception as e:
        errors.append(f"sitemap:{type(e).__name__}:{e}")

    seen = set()
    for url, hinted_title in pages:
        if url in seen:
            continue
        seen.add(url)
        if len(seen) > 14:
            break
        try:
            raw = _gch_fetch_text(url)
            text = _gch_visible_text(raw)
            title = _gch_page_title(raw) or hinted_title
            is_local = "地方競馬" in title and "中継" in title
            is_overseas = "海外競馬" in text and "中継" in title
            if not (is_local or is_overseas):
                continue
            if not _gch_today_in_broadcast_time(text, now):
                continue
            broadcasts.append(
                {
                    "kind": "local" if is_local else "overseas",
                    "title": title,
                    "url": url,
                }
            )
        except Exception as e:
            errors.append(f"{hinted_title}:{type(e).__name__}:{e}")
    return broadcasts, errors


def _gch_jra_race_day(now: datetime) -> tuple[bool, list[str], str | None]:
    try:
        bucket = int(time.time() // 300)
        raw = _gch_fetch_text(f"{GCH_VERIFIED_STATUS}?v={bucket}", timeout=10)
        cfg = json.loads(raw)
        ids = [str(x) for x in cfg.get("jra_active_ids", [])]
        same_day = cfg.get("date") == now.date().isoformat()
        active = [x for x in ids if x in {"jra.east", "jra.west", "jra.hokkaido", "jra.local"}]
        return bool(same_day and active), active, None
    except Exception as e:
        return False, [], f"{type(e).__name__}:{e}"


def gch_status(force: bool = False) -> dict:
    now = datetime.now(GCH_JST)
    if not force and GCH_CACHE["value"] is not None and time.time() - GCH_CACHE["at"] < 300:
        return GCH_CACHE["value"]

    jra_race_day, jra_active_ids, jra_error = _gch_jra_race_day(now)
    broadcasts, source_errors = _gch_special_broadcasts(now)
    local = any(x["kind"] == "local" for x in broadcasts)
    overseas = any(x["kind"] == "overseas" for x in broadcasts)
    value = {
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "jra_race_day": jra_race_day,
        "jra_active_ids": jra_active_ids,
        "local_race_broadcast": local,
        "overseas_race_broadcast": overseas,
        "show_gch_main": bool(jra_race_day or local or overseas),
        "broadcasts": broadcasts,
        "source": {
            "jra": "ajiousama/himitsu verified_daily_status.json",
            "gch": "greenchannel.jp official programme pages",
        },
        "errors": ([f"jra:{jra_error}"] if jra_error else []) + source_errors,
    }
    GCH_CACHE["at"] = time.time()
    GCH_CACHE["value"] = value
    return value


core.auth = cloud_auth
core.BUILD = "20260909-radio-tv-audio-sync-v2"
_original_do_get = core.Handler.do_GET


def _cloud_do_get(self):
    parsed = urllib.parse.urlsplit(self.path)
    path = parsed.path
    if path == "/gch-status":
        force = urllib.parse.parse_qs(parsed.query).get("refresh", ["0"])[0] in {"1", "true", "yes"}
        payload = json.dumps(gch_status(force=force), ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
        self.send_bytes(200, payload, "application/json; charset=utf-8"); return
    if radio_tv is not None and radio_tv.handle_request(self): return
    if radio_tv is None and (path.startswith("/radio-tv/") or path.startswith("/radio-art/") or path.startswith("/radio-debug/") or path.startswith("/radio-file-debug/")):
        self.send_bytes(503, f"radio-tv unavailable: {RADIO_TV_IMPORT_ERROR or 'dependency import failed'}\n".encode(), "text/plain; charset=utf-8"); return
    if path == "/vpncheck":
        self.send_bytes(200, tun_capability_report().encode(), "text/plain; charset=utf-8"); return
    return _original_do_get(self)


core.Handler.do_GET = _cloud_do_get


def _cloud_do_head(self):
    path = urllib.parse.urlsplit(self.path).path
    if path.startswith("/radio-tv/"):
        self.send_response(200); self.send_header("Content-Type", "video/mp2t"); self.send_header("Cache-Control", "no-store"); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); return
    if path in {"/health", "/gch-status"}:
        self.send_response(200); self.send_header("Content-Type", "application/json; charset=utf-8" if path == "/gch-status" else "text/plain; charset=utf-8"); self.end_headers(); return
    self.send_response(405); self.send_header("Allow", "GET, HEAD"); self.end_headers()


core.Handler.do_HEAD = _cloud_do_head

if __name__ == "__main__":
    core.main()
