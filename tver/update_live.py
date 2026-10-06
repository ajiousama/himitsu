#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36"
BASE = "https://platform-api.tver.jp/service/api/v1"
BROWSER = "https://platform-api.tver.jp/v2/api/platform_users/browser/create"
PLAYER_INFO = "https://player.tver.jp/player/streaks_info_v2.json"
PLAYBACK = "https://playback.api.streaks.jp/v1/projects/{project}/medias/{media}"
SSAI = "https://ssai.api.streaks.jp/v1/projects/{project}/medias/{media}/ssai/session"
OUT = Path("tver/playlist.m3u")
STATUS = Path("tver/live_status.json")
TIMEOUT = 15

PUBLIC_TVER_PLAYLISTS = [
    "https://raw.githubusercontent.com/david13xa/-/main/irl.m3u",
    "https://raw.githubusercontent.com/dbghelp/Free-to-air-TV/master/japan.m3u8",
]

STABLE_SIMUL = {
    "ntv": "https://live-tver-simul-ntv.streaks.jp/938232e586b34196b704a5839663984b/cb593b5eafbb4645907e979d757e1dd5/manifest_1.m3u8",
    "ex": "https://live-tver-simul-ex.streaks.jp/498c4512f66846f1b0a5a3320ee035c3/ce98cb0b48994b50a76dba08ea894e24/manifest_1.m3u8",
    "tbs": "https://live-tver-simul-tbs.streaks.jp/8e4c80725b9842cdb0f6f91260945222/b72f7e116957436b824f95d5138ea7a3/manifest_1.m3u8",
    "tx": "https://live-tver-simul-tx.streaks.jp/035622a82bcb46bc8e41ca5351f95a00/3887c96991ce4ae1bec43ea19f24c4d5/manifest_1.m3u8",
    "cx": "https://live-tver-simul-cx.streaks.jp/a78ebf1910144ba287907ec691bdc863/4817bf371f214463a3609e17a365f098/manifest_1.m3u8",
}

KNOWN_SPECIALS = {
    "le7gtytdy0": {
        "name": "Tver 日テレ NEWS24",
        "tvg_id": "tver.news24",
        "logo": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver.news24_ecf50e0e.png",
    },
    "le5t0u6hpv": {
        "name": "Tver TBS NEWS DIG",
        "tvg_id": "tver.tbs_newsdig",
        "logo": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver.tbs_newsdig_65e73997.png",
    },
}

NETWORK_LOGOS = {
    "ntv": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver_ntv_c8f6e09c.png",
    "tbs": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver_tbs_3c5293a7.png",
    "ex": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver_ex_55fa4b5f.png",
    "tx": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver_tx_f8743784.png",
    "cx": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver_cx_71e6080a.png",
}

S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept": "application/json,text/plain,*/*",
    "Referer": "https://tver.jp/",
    "Origin": "https://tver.jp",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
})


def get_json(url, *, headers=None):
    r = S.get(url, headers=headers or {}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def browser_credentials():
    r = S.post(
        BROWSER,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://s.tver.jp/",
        },
        data="device_type=pc",
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    d = r.json().get("result") or {}
    uid = d.get("platform_uid")
    token = d.get("platform_token")
    if not uid or not token:
        raise RuntimeError("TVer browser credentials missing")
    return uid, token


def platform(path, uid, token):
    return get_json(
        f"{BASE}/{path}",
        headers={"x-tver-platform-type": "web"},
    ) if False else _platform(path, uid, token)


def _platform(path, uid, token):
    r = S.get(
        f"{BASE}/{path}",
        params={"platform_uid": uid, "platform_token": token},
        headers={"x-tver-platform-type": "web"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def all_objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from all_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from all_objects(child)


def is_active(start_at, end_at, now):
    try:
        start = int(start_at or 0)
        end = int(end_at or 0)
    except (TypeError, ValueError):
        return True
    if start and now < start:
        return False
    if end and now >= end:
        return False
    return True


def discover_specials(uid, token):
    now = int(time.time())
    found = {}
    try:
        home = platform("callHome", uid, token)
        for obj in all_objects(home):
            if obj.get("type") != "live":
                continue
            c = obj.get("content")
            if not isinstance(c, dict):
                continue
            live_id = str(c.get("id") or "").strip()
            if not re.fullmatch(r"le[a-z0-9]+", live_id, re.I):
                continue
            if not is_active(c.get("startAt"), c.get("endAt"), now):
                continue
            found[live_id] = {
                "id": live_id,
                "title": str(c.get("title") or c.get("seriesTitle") or live_id).strip(),
                "series_title": str(c.get("seriesTitle") or "").strip(),
                "start_at": c.get("startAt"),
                "end_at": c.get("endAt"),
                "live_type": c.get("liveType"),
                "kind": "special",
            }
    except Exception as exc:
        print(f"::warning::callHome special discovery failed: {exc}")

    for live_id, meta in KNOWN_SPECIALS.items():
        found.setdefault(live_id, {
            "id": live_id,
            "title": meta["name"].replace("Tver ", ""),
            "series_title": "",
            "start_at": None,
            "end_at": None,
            "live_type": "continuous",
            "kind": "special",
        })
    return list(found.values())


def current_key_names():
    month = time.localtime(time.time() + 9 * 3600).tm_mon
    preferred = f"key{(month % 6 or 6):02d}"
    names = [f"key{i:02d}" for i in range(1, 7)]
    if preferred in names:
        names.remove(preferred)
        names.insert(0, preferred)
    return names


def source_list(media):
    sources = media.get("sources") if isinstance(media, dict) else None
    if isinstance(sources, dict):
        return [sources]
    if isinstance(sources, list):
        return [x for x in sources if isinstance(x, dict)]
    return []


def source_is_hls(src):
    raw = str(src.get("src") or "")
    typ = str(src.get("type") or "").lower()
    if not raw.startswith("https://"):
        return False
    if src.get("key_systems") or src.get("keySystems"):
        return False
    return ".m3u8" in raw.lower() or "mpegurl" in typ


def ssai_enabled(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.lower() not in ("", "false", "0", "disabled", "none")
    if isinstance(value, dict):
        if "enabled" in value:
            return ssai_enabled(value["enabled"])
        return bool(value)
    return False


def sessionized(url):
    return bool(re.search(r"[?&]session=[^&]+", url, re.I))


def default_ads_params(current_id=""):
    empty_keys = [
        "tvcu_pcode","tvcu_ccode","tvcu_zcode","tvcu_gender","tvcu_gender_code",
        "tvcu_age","tvcu_agegrp","rdid","idtype","is_lat","bundle","interest",
        "item_eventid","item_programkey","item_category","item_episodecode",
        "item_originalmeta1","item_originalmeta2","ntv_ppid","tbs_ppid","tx_ppid",
        "ex_ppid","cx_ppid_gam","mbs_ppid_gam","abc_ppid","tvo_ppid","ktv_ppid",
        "ytv_ppid","ntv_ppid2","tbs_ppid2","tx_ppid2","ex_ppid2","cx_ppid2",
        "mbs_ppid2","abc_ppid2","tvo_ppid2","ktv_ppid2","ytv_ppid2","vr_uuid",
        "platformAdUid","platformUid","accountId","memberId","memberIdHash","luid","platformVrUid",
        "tvcu_params","tvcu_params_e","tvcu_params_ee","tvcu_params_eee",
    ]
    p = {k: "" for k in empty_keys}
    p.update({
        "delivery_type": "simul",
        "is_dvr": "0",
        "video_id": current_id or "",
        "device": "pc",
        "device_code": "0001",
        "tag_type": "browser",
        "car": "0",
        "personalIsLat": "0",
        "c": "simul",
    })
    return p


def playable_special(live_id):
    meta = special_meta(live_id)
    live_video = meta.get("liveVideo") if isinstance(meta, dict) else {}
    if not isinstance(live_video, dict):
        live_video = {}

    project = str(live_video.get("projectID") or live_video.get("projectId") or "tver-splive")
    media_ref = str(live_video.get("mediaID") or live_video.get("mediaId") or f"ref:{live_id}")
    if not media_ref.startswith("ref:") and project == "tver-splive":
        media_ref = "ref:" + media_ref

    info = get_json(PLAYER_INFO)
    project_info = info.get(project) or info.get("tver-splive") or {}
    key_obj = project_info.get("api_key") if isinstance(project_info, dict) else {}
    if not isinstance(key_obj, dict):
        key_obj = {}

    keys = []
    direct_keys = [
        live_video.get("apiKey"),
        live_video.get("api_key"),
        (meta.get("streaks") or {}).get("apiKey") if isinstance(meta.get("streaks"), dict) else None,
        (meta.get("streaks") or {}).get("api_key") if isinstance(meta.get("streaks"), dict) else None,
        meta.get("apiKey"),
        meta.get("api_key"),
    ]
    for value in direct_keys:
        if isinstance(value, str) and value and value not in keys:
            keys.append(value)
    for name in current_key_names():
        value = key_obj.get(name)
        if isinstance(value, str) and value and value not in keys:
            keys.append(value)
    for value in key_obj.values():
        if isinstance(value, str) and value and value not in keys:
            keys.append(value)
    # Keep the legacy special-live key only as a final fallback.
    if live_id not in keys:
        keys.append(live_id)

    url = PLAYBACK.format(
        project=quote(project, safe=""),
        media=quote(media_ref, safe=":"),
    )
    last = None
    for key in keys:
        try:
            data = get_json(url, headers={"X-Streaks-Api-Key": key})
            media = data.get("media") if isinstance(data, dict) and isinstance(data.get("media"), dict) else data
            for src in source_list(media):
                if source_is_hls(src):
                    return str(src.get("src"))
        except Exception as exc:
            last = exc

    # Some special-live projects no longer require an explicit key.
    try:
        data = get_json(url)
        media = data.get("media") if isinstance(data, dict) and isinstance(data.get("media"), dict) else data
        for src in source_list(media):
            if source_is_hls(src):
                return str(src.get("src"))
    except Exception as exc:
        last = exc

    print(
        f"::warning::Special metadata {live_id}: "
        f"project={project} media={media_ref} "
        f"liveVideoKeys={sorted(live_video.keys())} "
        f"playerProjectFound={bool(project_info)} keyCandidates={len(keys)}"
    )
    raise RuntimeError(f"Special Live playback unavailable: {last}")


def normalize_channel(item):
    if not isinstance(item, dict):
        return None
    c = item.get("content") or {}
    v = item.get("video") or c.get("video") or {}
    if not isinstance(c, dict) or not isinstance(v, dict):
        return None
    cid = str(c.get("id") or "").strip()
    project = str(v.get("projectID") or v.get("projectId") or "").strip()
    media = str(v.get("mediaID") or v.get("mediaId") or "").strip()
    if not cid or not project or not media:
        return None
    return {
        "id": cid,
        "name": str(c.get("name") or cid).strip(),
        "project": project,
        "media": media,
        "api_key_name": str(v.get("apiKey") or cid).strip(),
    }


def current_program(channel_id, uid, token):
    now = int(time.time())
    data = platform(f"callLiveTimeline/{quote(channel_id, safe='')}", uid, token)
    items = ((data.get("result") or {}).get("contents") or [])
    for item in items:
        if not isinstance(item, dict):
            continue
        c = item.get("content") or {}
        try:
            start = int(c.get("startAt") or 0)
            end = int(c.get("endAt") or 0)
        except (TypeError, ValueError):
            continue
        if start <= now < end:
            text = f"{c.get('title') or ''} {c.get('seriesTitle') or ''}"
            paused = item.get("type") == "pause" or "配信休止" in text or "配信準備中" in text
            if paused:
                return None
            return c
    return None


def resolve_simul(channel, current):
    stable = STABLE_SIMUL.get(channel["id"].lower())
    if stable:
        return stable

    info = get_json(PLAYER_INFO)
    project_info = (
        info.get(channel["project"])
        or info.get(f'tver-{channel["api_key_name"]}')
        or info.get(channel["api_key_name"])
        or {}
    )
    key_obj = project_info.get("api_key") or {}
    api_keys = [key_obj.get(k) for k in current_key_names() if key_obj.get(k)]
    if not api_keys:
        api_keys = [v for v in key_obj.values() if isinstance(v, str) and v]
    if not api_keys:
        raise RuntimeError("no Streaks API key")

    media_ref = channel["media"]
    if not media_ref.startswith("ref:"):
        media_ref = "ref:" + media_ref
    url = PLAYBACK.format(
        project=quote(channel["project"], safe=""),
        media=quote(media_ref, safe=":"),
    )

    data = None
    last = None
    for key in api_keys:
        try:
            data = get_json(url, headers={"X-Streaks-Api-Key": key})
            break
        except Exception as exc:
            last = exc
    if data is None:
        raise RuntimeError(f"playback rejected all keys: {last}")

    media = data.get("media") if isinstance(data, dict) and isinstance(data.get("media"), dict) else data
    sources = [x for x in source_list(media) if source_is_hls(x)]
    if not sources:
        raise RuntimeError("no clear HLS source")

    preferred = sources[0]
    raw = str(preferred.get("src") or "")
    media_ssai = ssai_enabled(media.get("ssai") if isinstance(media, dict) else None)
    candidates = [
        x for x in sources
        if (media_ssai or ssai_enabled(x.get("ssai")))
        and not sessionized(str(x.get("src") or ""))
        and x.get("id")
    ]

    if not candidates:
        return raw

    wire_project = str(
        media.get("project") or media.get("projectId") or media.get("project_id")
        or channel["project"]
    )
    wire_media = str(
        media.get("mediaId") or media.get("id") or media.get("media_id")
        or media.get("ref_id") or ""
    )
    if not wire_media:
        return raw

    session_url = SSAI.format(
        project=quote(wire_project, safe=""),
        media=quote(wire_media, safe=":"),
    )
    source_ids = [str(x["id"]) for x in candidates]
    ads = default_ads_params(str(current.get("id") or ""))
    ad_fields = media.get("ad_fields") or media.get("adFields") or {}
    if isinstance(ad_fields, dict):
        ads.update(ad_fields)

    r = S.post(
        session_url,
        json={"ads_params": ads, "id": ",".join(source_ids)},
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    entries = r.json()
    if not isinstance(entries, list):
        return raw
    by_id = {
        str(x.get("id")): str(x.get("query") or "")
        for x in entries if isinstance(x, dict)
    }
    for src in candidates:
        sid = str(src.get("id"))
        query = by_id.get(sid)
        raw_src = str(src.get("src") or "")
        if query:
            return raw_src + ("&" if "?" in raw_src else "?") + query
    return raw


def discover_simul(uid, token):
    data = platform("callLiveChannel", uid, token)
    items = ((data.get("result") or {}).get("contents") or [])
    out = []
    for item in items:
        ch = normalize_channel(item)
        if not ch:
            continue
        try:
            cur = current_program(ch["id"], uid, token)
            if not cur:
                continue
            url = resolve_simul(ch, cur)
            if not url:
                continue
            out.append({
                "id": ch["id"],
                "title": str(cur.get("title") or cur.get("seriesTitle") or ch["name"]).strip(),
                "series_title": str(cur.get("seriesTitle") or "").strip(),
                "channel_name": ch["name"],
                "url": url,
                "start_at": cur.get("startAt"),
                "end_at": cur.get("endAt"),
                "kind": "simul",
            })
        except Exception as exc:
            print(f"::warning::TVer simul {ch['id']} failed: {exc}")
    return out


def hls_ok(url):
    try:
        r = S.get(
            url,
            headers={"Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,*/*"},
            timeout=TIMEOUT,
        )
        return r.ok and "#EXTM3U" in r.text[:10000]
    except Exception:
        return False


def safe_id(text):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("_") or "live"


def special_meta(live_id):
    for version in (3, 2, 1):
        try:
            return get_json(f"https://statics.tver.jp/content/live/{quote(live_id)}.json?v={version}")
        except Exception:
            pass
    return {}



def clean_public_name(name):
    name = re.sub(r"\s+", " ", str(name or "")).strip()
    aliases = {
        "NTV NEWS24": "Tver 日テレ NEWS24",
        "日テレNEWS24": "Tver 日テレ NEWS24",
        "TBS NEWS DIG": "Tver TBS NEWS DIG",
        "TBS NEWS DIG Powered by JNN": "Tver TBS NEWS DIG",
        "日テレNEWS NNN": "Tver 日テレNEWS NNN",
    }
    return aliases.get(name, f"Tver {name}" if name and not name.lower().startswith("tver") else name)


def public_live_candidates():
    rows = []
    seen = set()
    for source in PUBLIC_TVER_PLAYLISTS:
        try:
            r = S.get(source, timeout=TIMEOUT)
            r.raise_for_status()
            lines = r.text.splitlines()
        except Exception as exc:
            print(f"::warning::public TVer playlist failed {source}: {exc}")
            continue

        pending = None
        for line in lines:
            line = line.strip()
            if line.startswith("#EXTINF:"):
                pending = line
                continue
            if not pending or not line.startswith("https://"):
                continue

            url = line
            # Realtime TVer channels other than the five simulcast networks.
            if "streaks.jp" not in url or "live-tver-" not in url:
                pending = None
                continue
            if "live-tver-simul-" in url:
                pending = None
                continue

            name = pending.split(",", 1)[1].strip() if "," in pending else "TVer Live"
            key = url.split("?", 1)[0]
            if key not in seen:
                seen.add(key)
                rows.append({
                    "name": clean_public_name(name),
                    "url": key,
                    "source": source,
                })
            pending = None
    return rows


def logo_for_live_name(name):
    n = str(name).lower()
    if "news24" in n:
        return "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver.news24_ecf50e0e.png"
    if "tbs" in n and "news" in n:
        return "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver.tbs_newsdig_65e73997.png"
    return ""


def known_tvg_id_for_live(name, url):
    n = str(name).lower()
    if "news24" in n:
        return "tver.news24"
    if "tbs" in n and "news" in n:
        return "tver.tbs_newsdig"
    if "news nnn" in n or "news-nnn" in url.lower():
        return "tver.news_nnn"
    return "tver.live." + safe_id(url.split("streaks.jp", 1)[0].rsplit("/", 1)[-1])


def build():
    uid, token = browser_credentials()
    specials = discover_specials(uid, token)
    simul = discover_simul(uid, token)
    rows = []

    for item in public_live_candidates():
        if not hls_ok(item["url"]):
            print(f"::warning::public TVer HLS failed: {item['name']}")
            continue
        rows.append({
            "tvg_id": known_tvg_id_for_live(item["name"], item["url"]),
            "name": item["name"].replace(",", " "),
            "logo": logo_for_live_name(item["name"]),
            "url": item["url"],
            "kind": "public-live",
            "source_id": item["url"].split("?", 1)[0],
        })

    status = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "special_discovered": len(specials),
        "simul_discovered": len(simul),
        "entries": [],
    }

    for item in specials:
        live_id = item["id"]
        title_hint = str(item.get("title") or "").lower()
        if (
            ("news24" in title_hint and any(r["tvg_id"] == "tver.news24" for r in rows))
            or ("tbs" in title_hint and "news" in title_hint and any(r["tvg_id"] == "tver.tbs_newsdig" for r in rows))
        ):
            continue
        try:
            url = playable_special(live_id)
            if not url or not hls_ok(url):
                raise RuntimeError("HLS probe failed")
            known = KNOWN_SPECIALS.get(live_id)
            meta = special_meta(live_id)
            title = (
                (known or {}).get("name")
                or item.get("title")
                or meta.get("title")
                or meta.get("seriesTitle")
                or live_id
            )
            if known:
                tvg_id = known["tvg_id"]
                logo = known["logo"]
            else:
                tvg_id = f"tver.special.{safe_id(live_id)}"
                logo = ""
            rows.append({
                "tvg_id": tvg_id,
                "name": str(title).replace(",", " "),
                "logo": logo,
                "url": url,
                "kind": "special",
                "source_id": live_id,
            })
        except Exception as exc:
            print(f"::warning::TVer special {live_id} failed: {exc}")

    for item in simul:
        url = item["url"]
        if not hls_ok(url):
            print(f"::warning::TVer simul {item['id']} HLS probe failed")
            continue
        cid = item["id"]
        rows.append({
            "tvg_id": f"tver.realtime.{safe_id(cid)}",
            "name": f"Tver {item['channel_name']}",
            "logo": NETWORK_LOGOS.get(cid.lower(), ""),
            "url": url,
            "kind": "simul",
            "source_id": cid,
            "program": item.get("title") or "",
        })

    # Deduplicate by stream/source identity. Prefer persistent known-news IDs first.
    unique = {}
    for row in rows:
        key = (row["kind"], row["source_id"])
        unique[key] = row
    rows = list(unique.values())
    rows.sort(key=lambda x: (0 if x["kind"] == "special" else 1, x["name"]))

    if not rows:
        raise SystemExit("No playable TVer live streams found; keeping previous playlist")

    lines = ["#EXTM3U", "", "### TVerﾘｱﾙﾀｲﾑ", ""]
    for row in rows:
        attrs = [
            f'tvg-id="{row["tvg_id"]}"',
            f'tvg-name="{row["name"]}"',
            'group-title="TVerﾘｱﾙﾀｲﾑ"',
        ]
        if row["logo"]:
            attrs.insert(2, f'tvg-logo="{row["logo"]}"')
        lines.append(f'#EXTINF:-1 {" ".join(attrs)},{row["name"]}')
        lines.append(row["url"])
        lines.append("")
        status["entries"].append(row)

    OUT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"TVer live updated: playable={len(rows)} "
        f"special={sum(r['kind'] in ('special','public-live') for r in rows)} "
        f"simul={sum(r['kind']=='simul' for r in rows)}"
    )
    for row in rows:
        suffix = f" / {row.get('program')}" if row.get("program") else ""
        print(f"  {row['kind']}: {row['name']} [{row['source_id']}]{suffix}")


if __name__ == "__main__":
    build()
