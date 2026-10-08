#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import re
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests

FRONT = "https://channel.rakuten.co.jp"
API = "https://backendapi.channel.rakuten.co.jp/platform/content/channels"
PLAYLIST = Path("rakuten/playlist.m3u")
STATUS = Path("rakuten/live_refresh_status.json")
NEEDS_BROWSER = Path("rakuten/needs_browser_refresh")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
HEADERS = {
    "User-Agent": UA,
    "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,application/json,text/plain,*/*",
    "Origin": FRONT,
    "Referer": FRONT + "/",
}

TARGETS = {
    125: {"tvg_id": "rch_125", "title": "セクシーエンタメチャンネル"},
    124: {"tvg_id": "rch_124", "title": "おとなの歓楽街 by MEN’S NECO"},
    121: {"tvg_id": "rch_41",  "title": "アイドル・グラビア"},
    123: {"tvg_id": "rch_123", "title": "刺激ストロング"},
    122: {"tvg_id": "rch_122", "title": "映画（年齢制限あり）"},
}

def add_query(url, extra):
    p = urlsplit(url)
    q = dict(parse_qsl(p.query, keep_blank_values=True))
    q.update(extra)
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), p.fragment))

def first_media_uri(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            for nxt in lines[i + 1:]:
                if not nxt.startswith("#"):
                    return nxt, "child"
    for line in lines:
        if not line.startswith("#"):
            return line, "segment"
    return None, None

def get(session, url, max_bytes=131072):
    with session.get(url, headers=HEADERS, timeout=(5, 10), allow_redirects=True, stream=True) as r:
        data = b""
        for chunk in r.iter_content(8192):
            if chunk:
                data += chunk
                if len(data) >= max_bytes:
                    break
        return r.status_code, r.url, data, dict(r.headers)

def probe_hls(session, url):
    try:
        code, final, data, _ = get(session, url)
        if code != 200:
            return False, f"http_{code}", final
        text = data.decode("utf-8", "ignore")
        if "#EXTM3U" not in text:
            return False, "non_hls", final
        media, kind = first_media_uri(text)
        if not media:
            return True, "manifest_only", final
        media_url = urljoin(final, media)
        code2, final2, data2, _ = get(session, media_url, 65536)
        if code2 != 200:
            return False, f"{kind}_http_{code2}", final2
        if kind == "child":
            child = data2.decode("utf-8", "ignore")
            if "#EXTM3U" not in child:
                return False, "child_non_hls", final2
            seg, _ = first_media_uri(child)
            if not seg:
                return True, "child_manifest_only", final2
            seg_url = urljoin(final2, seg)
            code3, final3, data3, _ = get(session, seg_url, 32768)
            if code3 == 200 and data3:
                return True, "segment", final3
            return False, f"segment_http_{code3}", final3
        return bool(data2), "segment" if data2 else "empty_segment", final2
    except requests.RequestException as e:
        return False, type(e).__name__, None
    except Exception as e:
        return False, "error_" + type(e).__name__, None

def fetch_channels(session):
    session.get(FRONT + "/", headers=HEADERS, timeout=20)
    r = session.get(API, headers=HEADERS, params={"platform": "WEB"}, timeout=20)
    r.raise_for_status()
    payload = r.json()
    if payload.get("status") not in (None, 200) or not isinstance(payload.get("data"), list):
        raise RuntimeError("R Channel API returned no channel data")
    return {int(x["id"]): x for x in payload["data"] if isinstance(x, dict) and str(x.get("id", "")).isdigit()}

def load_browser_urls(path):
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj.get("channels", obj) if isinstance(obj, dict) else {}

def current_url_by_tvg_id(text, tvg_id):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXTINF") and f'tvg-id="{tvg_id}"' in line:
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].startswith("#")):
                j += 1
            return lines[j].strip() if j < len(lines) else None
    return None

def replace_url_by_tvg_id(text, tvg_id, new_url):
    lines = text.splitlines()
    changed = False
    for i, line in enumerate(lines):
        if line.startswith("#EXTINF") and f'tvg-id="{tvg_id}"' in line:
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].startswith("#")):
                j += 1
            if j < len(lines) and lines[j].strip() != new_url:
                lines[j] = new_url
                changed = True
            break
    suffix = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + suffix, changed

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--browser-json", default="")
    ap.add_argument("--api-only", action="store_true")
    args = ap.parse_args()

    now = dt.datetime.now(dt.timezone.utc)
    session = requests.Session()
    channels = fetch_channels(session)
    browser = load_browser_urls(args.browser_json)
    original = PLAYLIST.read_text(encoding="utf-8-sig")
    updated = original
    session_uuid = str(uuid.uuid4())

    report = {
        "checked_at_utc": now.isoformat(),
        "source": API + "?platform=WEB",
        "session_uuid": session_uuid,
        "channels": {},
        "all_resolved": True,
    }

    for channel_id, meta in TARGETS.items():
        item = channels.get(channel_id)
        if not item:
            report["channels"][str(channel_id)] = {"ok": False, "reason": "missing_from_api", **meta}
            report["all_resolved"] = False
            continue
        base = str(item.get("manifestUrl") or "").strip()
        if not base:
            report["channels"][str(channel_id)] = {"ok": False, "reason": "missing_manifest", **meta}
            report["all_resolved"] = False
            continue

        candidates = []
        b = browser.get(str(channel_id)) or browser.get(meta["title"]) or browser.get(meta["tvg_id"])
        if isinstance(b, str) and b.startswith("http"):
            candidates.append(("browser", b))

        candidates.append(("api", base))
        candidates.append(("api_rchweb", add_query(base, {
            "ads.device_make": "rchweb",
            "ads.url": "channel.rakuten.co.jp",
            "ads.refid": "0",
        })))
        candidates.append(("api_session", add_query(base, {
            "ads.device_make": "rchweb",
            "ads.url": "channel.rakuten.co.jp",
            "ads.uuid": session_uuid,
            "ads.uid_rch": session_uuid,
            "ads.refid": "0",
            "ads.rch_hid": "",
        })))

        seen = set()
        chosen = None
        attempts = []
        for label, cand in candidates:
            if cand in seen:
                continue
            seen.add(cand)
            ok, reason, final = probe_hls(session, cand)
            attempts.append({"source": label, "ok": ok, "reason": reason})
            if ok:
                chosen = (label, cand)
                break

        current = current_url_by_tvg_id(updated, meta["tvg_id"])
        entry = {
            **meta,
            "api_id": channel_id,
            "api_title": item.get("title"),
            "platform": item.get("platform"),
            "rating": item.get("rating"),
            "genre": item.get("genreName"),
            "attempts": attempts,
            "selected_source": chosen[0] if chosen else None,
            "changed": False,
        }
        if chosen:
            updated, changed = replace_url_by_tvg_id(updated, meta["tvg_id"], chosen[1])
            entry["changed"] = changed
            entry["ok"] = True
        else:
            entry["ok"] = False
            entry["reason"] = "no_playable_candidate"
            entry["kept_previous"] = bool(current)
            report["all_resolved"] = False
        report["channels"][str(channel_id)] = entry

    STATUS.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if report["all_resolved"]:
        NEEDS_BROWSER.unlink(missing_ok=True)
    else:
        NEEDS_BROWSER.write_text("browser refresh required\n", encoding="utf-8")

    if updated != original:
        PLAYLIST.write_text(updated, encoding="utf-8", newline="\n")

    print(json.dumps({
        "all_resolved": report["all_resolved"],
        "channels": {
            k: {
                "title": v.get("title"),
                "ok": v.get("ok"),
                "selected_source": v.get("selected_source"),
                "changed": v.get("changed"),
                "attempts": v.get("attempts", []),
            }
            for k, v in report["channels"].items()
        },
    }, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
