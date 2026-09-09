from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import json
import re
import subprocess
from urllib.parse import urlsplit

FREEWIFI = Path("freewifi")
GENERAL = Path("general_youtube.m3u")
OUT = Path("kana_tube.m3u")
STATUS = Path("kana_tube_status.json")
COOKIES = Path("youtube_cookies.txt")

HANDLE = "@kana_tube"
CHANNEL_ID = "UCmHdGDdZGf4cMWRBmEw4Xww"
CHANNEL = f"https://www.youtube.com/{HANDLE}"
TVG_ID = "youtube.kana_tube"
NAME = "かなチューブ"
LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/yt43_01_kana_tube.png"
START = "# === KANA_TUBE_MANAGED_START ==="
END = "# === KANA_TUBE_MANAGED_END ==="
GENERAL_START = "# === GENERAL_YOUTUBE_MANAGED_START ==="
JST = ZoneInfo("Asia/Tokyo")


def base_cmd():
    cmd = [
        "yt-dlp", "--js-runtimes", "node", "--no-warnings", "--no-cache-dir",
        "--socket-timeout", "12", "--retries", "1",
    ]
    if COOKIES.exists() and COOKIES.stat().st_size > 20:
        cmd += ["--cookies", str(COOKIES)]
    return cmd


def run_json(args, timeout=45):
    try:
        p = subprocess.run(base_cmd() + args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout"

    # yt-dlp can emit useful metadata for an upcoming live reservation while
    # still returning non-zero because no playable formats exist yet. Parse
    # stdout first so a reservation frame is not thrown away as an error.
    if p.stdout.strip():
        try:
            return json.loads(p.stdout), None
        except Exception:
            pass

    if p.returncode != 0:
        err = " | ".join(x.strip() for x in p.stderr.splitlines()[-3:] if x.strip())
        return None, err[:600]
    return None, "invalid-json"


def official(info):
    cid = (info.get("channel_id") or "").strip()
    if cid:
        return cid == CHANNEL_ID
    for key in ("channel_url", "uploader_url"):
        parsed = urlsplit(info.get(key) or "")
        if parsed.hostname in ("www.youtube.com", "youtube.com") and parsed.path.rstrip('/').lower() == '/' + HANDLE.lower():
            return True
    return False


def inspect_watch(video_id):
    # --ignore-no-formats-error is important for future live reservations.
    return run_json([
        "--dump-single-json", "--no-playlist", "--ignore-no-formats-error",
        f"https://www.youtube.com/watch?v={video_id}",
    ], timeout=35)


def listing_ids(url, limit=30):
    try:
        p = subprocess.run(
            base_cmd() + [
                "--flat-playlist", "--dump-json", "--playlist-end", str(limit), url,
            ],
            capture_output=True,
            text=True,
            timeout=45,
        )
    except subprocess.TimeoutExpired:
        return [], "timeout"

    if p.returncode != 0 and not p.stdout.strip():
        err = " | ".join(x.strip() for x in p.stderr.splitlines()[-3:] if x.strip())
        return [], err[:600]

    live, upcoming, other = [], [], []
    for line in p.stdout.splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        vid = item.get("id")
        if not vid:
            continue
        st = (item.get("live_status") or "").lower()
        if st == "is_live":
            live.append(vid)
        elif st == "is_upcoming":
            upcoming.append(vid)
        elif st != "was_live":
            other.append(vid)
    return live + upcoming + other[:8], ("partial-listing" if p.returncode else None)


def search_ids():
    ids = []
    for query in (
        "ytsearchdate12:華奈tube 競輪",
        "ytsearchdate12:かなチューブ 競輪",
    ):
        found, _ = listing_ids(query, 12)
        ids.extend(found)
    return list(dict.fromkeys(ids))


def start_timestamp(info):
    # release_timestamp is normally the scheduled start for an upcoming live.
    for key in ("release_timestamp", "timestamp"):
        try:
            value = int(info.get(key) or 0)
        except Exception:
            value = 0
        if value > 0:
            return value
    return None


def choose_current(previous=None):
    candidates = []
    diagnostics = []
    reachable = False
    streams_confirmed = False
    inspections_failed = False
    if previous and previous.get("video_id"):
        candidates.append(previous["video_id"])

    # Reservation/upcoming frames normally appear in /streams before LIVE.
    # Scan deeper around the night window because the channel can expose both
    # daytime and nighttime reservations on the same day.
    now_jst = datetime.now(JST)
    night_focus = (19 <= now_jst.hour <= 23) or (0 <= now_jst.hour < 1)
    scan_limit = 60 if night_focus else 40
    for url in (CHANNEL + "/streams", CHANNEL + "/live", CHANNEL + "/videos"):
        ids, err = listing_ids(url, scan_limit)
        if not err:
            reachable = True
            if url.endswith("/streams"):
                streams_confirmed = True
        else:
            diagnostics.append(f"{url}: {err}")
        candidates.extend(ids)

    # Search is fallback only. Every result is still verified as the official
    # channel before it can be published.
    if not candidates:
        candidates.extend(search_ids())

    seen = set()
    items = []
    for vid in candidates:
        if vid in seen:
            continue
        seen.add(vid)
        info, err = inspect_watch(vid)
        if err or not info:
            inspections_failed = True
            if err:
                diagnostics.append(f"{vid}: {err}")
            continue
        reachable = True
        if not official(info):
            continue
        status = (info.get("live_status") or "").lower()
        if status not in ("is_live", "is_upcoming"):
            continue
        items.append(info)

    if not items:
        return None, streams_confirmed and not inspections_failed, diagnostics

    live = [x for x in items if (x.get("live_status") or "").lower() == "is_live"]
    if live:
        live.sort(key=lambda x: start_timestamp(x) or 0, reverse=True)
        return live[0], True, diagnostics

    now = int(datetime.now(timezone.utc).timestamp())
    future = sorted(
        items,
        key=lambda x: (
            0 if (start_timestamp(x) or now) >= now - 6 * 3600 else 1,
            abs((start_timestamp(x) or now) - now),
        ),
    )
    return future[0], True, diagnostics


def direct_live_url(info):
    manifest = (info.get("manifest_url") or "").strip()
    if manifest.startswith(("http://", "https://")):
        return manifest
    vid = info.get("id")
    if not vid:
        return None
    try:
        p = subprocess.run(
            base_cmd() + [
                "--no-playlist", "--match-filter", "is_live",
                "-f", "best[protocol^=m3u8]", "-g",
                f"https://www.youtube.com/watch?v={vid}",
            ],
            capture_output=True,
            text=True,
            timeout=35,
        )
    except subprocess.TimeoutExpired:
        return None
    urls = [
        x.strip() for x in p.stdout.splitlines()
        if x.strip().startswith(("http://", "https://"))
    ]
    return urls[0] if p.returncode == 0 and len(urls) == 1 else None


def jst_text(ts):
    if not ts:
        return None
    return datetime.fromtimestamp(ts, JST).isoformat(timespec="seconds")


def entry(url, state, ts=None):
    if state == "is_live":
        suffix = "【LIVE】"
    else:
        when = datetime.fromtimestamp(ts, JST).strftime("%m/%d %H:%M") if ts else ""
        suffix = f"【配信予定 {when}】" if when else "【配信予定】"
    label = NAME + suffix
    return "\n".join([
        f'#EXTINF:-1 tvg-id="{TVG_ID}" tvg-name="{NAME}" tvg-logo="{LOGO}" group-title="一般YouTube LIVE",{label}',
        url,
    ])


def strip_entry(text):
    text = re.sub(
        re.escape(START) + r".*?" + re.escape(END) + r"\n?",
        "",
        text,
        flags=re.S,
    )
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:") and f'tvg-id="{TVG_ID}"' in line:
            i += 1
            while i < len(lines) and not lines[i].startswith("#EXTINF:"):
                if lines[i].strip().startswith(("http://", "https://")):
                    i += 1
                    break
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out).rstrip() + "\n"


def sync_general(payload):
    base = GENERAL.read_text(encoding="utf-8-sig", errors="replace") if GENERAL.exists() else "#EXTM3U\n"
    base = strip_entry(base)
    if not base.strip():
        base = "#EXTM3U\n"
    if payload:
        base = base.rstrip() + "\n\n" + payload + "\n"
    GENERAL.write_text(base, encoding="utf-8")


def sync_freewifi(payload):
    base = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace") if FREEWIFI.exists() else "#EXTM3U\n"
    base = strip_entry(base)
    if not payload:
        FREEWIFI.write_text(base, encoding="utf-8")
        return
    block = START + "\n" + payload + "\n" + END + "\n"
    pos = base.find(GENERAL_START)
    if pos >= 0:
        base = base[:pos].rstrip() + "\n\n" + block + "\n" + base[pos:]
    else:
        base = base.rstrip() + "\n\n" + block
    FREEWIFI.write_text(base, encoding="utf-8")


def write_status(data):
    data["checked_at"] = datetime.now(JST).isoformat(timespec="seconds")
    STATUS.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def publish_snapshot(directory):
    """Overlay only Kana's owned entry onto the latest shared playlists."""
    directory = Path(directory)
    status = json.loads((directory / STATUS.name).read_text(encoding='utf-8'))
    if status.get('state') == 'error':
        # A failed check cannot restore an older playlist over a newer update.
        latest = read_status()
        latest.update({key: status[key] for key in ('state', 'checked_at', 'message', 'diagnostics') if key in status})
        STATUS.write_text(json.dumps(latest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        return
    output = (directory / OUT.name).read_text(encoding='utf-8')
    payload = '\n'.join(line for line in output.splitlines() if not line.startswith('#EXTM3U')).strip() or None
    OUT.write_text(output, encoding='utf-8')
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    sync_general(payload)
    sync_freewifi(payload)


def read_status():
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def validate_outputs():
    state = read_status().get("state")
    for path in (OUT, GENERAL, FREEWIFI):
        text = path.read_text(encoding="utf-8-sig")
        entries = [line for line in text.splitlines() if line.startswith("#EXTINF:") and f'tvg-id="{TVG_ID}"' in line]
        if len(entries) > 1:
            raise ValueError(f"duplicate Kana entry: {path}")
        if state == 'none' and entries:
            raise ValueError(f"offline Kana entry remains: {path}")
        if state in ('is_live', 'is_upcoming') and len(entries) != 1:
            raise ValueError(f"Kana entry missing: {path}")
        if any(f'tvg-logo="{LOGO}"' not in line for line in entries):
            raise ValueError(f"Kana logo mismatch: {path}")


def main():
    previous = read_status()
    selected, reachable, diagnostics = choose_current(previous)

    if selected is None and not reachable:
        # Never erase a working entry because YouTube/yt-dlp temporarily failed.
        write_status({
            **previous,
            "state": "error",
            "channel": HANDLE,
            "channel_id": CHANNEL_ID,
            "message": "YouTube確認失敗。既存エントリを保持",
            "diagnostics": diagnostics[-8:],
        })
        print("KANA: YouTube確認失敗。既存エントリを保持")
        return

    if selected is None:
        OUT.write_text("#EXTM3U\n", encoding="utf-8")
        sync_general(None)
        sync_freewifi(None)
        write_status({
            "state": "none",
            "channel": HANDLE,
            "channel_id": CHANNEL_ID,
            "message": "現在LIVE/配信予定なし",
            "diagnostics": diagnostics[-8:],
        })
        print("KANA: 現在LIVE/配信予定なし")
        return

    state = (selected.get("live_status") or "").lower()
    vid = selected.get("id")
    watch = f"https://www.youtube.com/watch?v={vid}"
    direct = direct_live_url(selected) if state == "is_live" else None
    if state == "is_live" and not direct:
        write_status({**previous, "state": "error", "channel": HANDLE,
                      "channel_id": CHANNEL_ID, "video_id": vid, "watch_url": watch,
                      "message": "LIVE確認済み・HLS取得失敗。既存エントリを保持",
                      "diagnostics": diagnostics[-8:]})
        print("KANA: LIVE確認済み・HLS取得失敗。再試行が必要")
        return
    play = direct or watch
    ts = start_timestamp(selected)
    payload = entry(play, state, ts)

    OUT.write_text("#EXTM3U\n" + payload + "\n", encoding="utf-8")
    sync_general(payload)
    sync_freewifi(payload)

    write_status({
        "state": state,
        "channel": HANDLE,
        "channel_id": CHANNEL_ID,
        "video_id": vid,
        "watch_url": watch,
        "play_url": play,
        "direct_hls": bool(direct),
        "title": selected.get("title") or NAME,
        "start_timestamp": ts,
        "start_jst": jst_text(ts),
        "diagnostics": diagnostics[-8:],
    })
    print(f"KANA: {state} {vid} {selected.get('title') or NAME}")
    print(f"KANA: direct_hls={bool(direct)}")


if __name__ == "__main__":
    main()
