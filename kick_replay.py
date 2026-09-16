#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

CONFIG = Path("kick_channels.json")
OUT_JSON = Path("kick_replay.json")
OUT_M3U = Path("kick_replay.m3u")
JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
REPLAY_BASE = "https://kick-resolver.onrender.com/kick?vod="
MAX_VODS_PER_CHANNEL = 12


def get_json(url: str):
    headers = {"User-Agent": UA, "Accept": "application/json, text/plain, */*", "Referer": "https://kick.com/", "Cache-Control": "no-cache", "Pragma": "no-cache"}
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            print(f"GET failed {url} attempt={attempt + 1}: {exc}")
            if attempt < 2: time.sleep(2 * (attempt + 1))
    return None


def walk(value):
    if isinstance(value, dict):
        yield value
        for v in value.values(): yield from walk(v)
    elif isinstance(value, list):
        for v in value: yield from walk(v)


def first_str(obj, keys):
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip(): return value.strip()
    return None


def looks_like_vod_id(value): return bool(value and re.fullmatch(r"[A-Za-z0-9_-]{6,120}", value))


def extract_candidates(payload):
    found, seen = [], set()
    for obj in walk(payload):
        vod_id = first_str(obj, ("uuid", "video_uuid", "videoUuid"))
        if not vod_id:
            candidate = obj.get("id")
            if isinstance(candidate, str) and looks_like_vod_id(candidate): vod_id = candidate
        if not looks_like_vod_id(vod_id) or vod_id in seen: continue
        blob = json.dumps(obj, ensure_ascii=False).lower()
        if not any(k in blob for k in ("video", "livestream", "duration", "thumbnail", "source", "created_at", "start")): continue
        seen.add(vod_id); found.append({"vod_id": vod_id, "raw": obj})
    return found


def iso_to_dt(text):
    if not text: return None
    try: return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception: return None


def find_in_tree(value, keys):
    for obj in walk(value):
        for key in keys:
            v = obj.get(key)
            if v not in (None, ""): return v
    return None


def clean_title(value, fallback): return re.sub(r"\s+", " ", (value or fallback).replace("\n", " ").replace("\r", " ").strip())[:180]


def normalize_duration(value):
    try: raw = int(value) if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()) else None
    except Exception: return None
    if raw is None: return None
    if raw > 7 * 24 * 60 * 60: return max(0, int(round(raw / 1000)))
    return max(0, raw)


def parse_gmcx_range(title):
    m = re.search(r"[＃#]\s*(\d+)\s*[-‐‑‒–—―〜~～]\s*(\d+)", title)
    if not m: return {}
    start, end = int(m.group(1)), int(m.group(2))
    if end < start or end - start > 100: return {}
    return {"episode_start": start, "episode_end": end, "episode_count": end-start+1}


def normalize_vod(vod_id, listed_obj, channel):
    detail = get_json(f"https://kick.com/api/v1/video/{urllib.parse.quote(vod_id)}") or listed_obj
    title = find_in_tree(detail, ("session_title", "title", "name")); created = find_in_tree(detail, ("created_at", "start_time", "started_at", "startTime")); end = find_in_tree(detail, ("ended_at", "end_time", "stopped_at", "endTime")); duration = find_in_tree(detail, ("duration", "duration_seconds", "length")); thumbnail = find_in_tree(detail, ("thumbnail", "thumbnail_url", "thumbnailUrl", "preview", "preview_url"))
    created_dt, end_dt = iso_to_dt(created if isinstance(created,str) else None), iso_to_dt(end if isinstance(end,str) else None)
    if created_dt and not created_dt.tzinfo: created_dt=created_dt.replace(tzinfo=timezone.utc)
    if end_dt and not end_dt.tzinfo: end_dt=end_dt.replace(tzinfo=timezone.utc)
    duration_s=normalize_duration(duration)
    if duration_s is None and created_dt and end_dt: duration_s=max(0,int((end_dt-created_dt).total_seconds()))
    mode="gmcx-ai" if str(channel.get("tvg_id") or "").startswith("kick.gccx") else "generic-vod"
    clean=clean_title(title if isinstance(title,str) else None, channel.get("name") or "KICK VOD")
    item={"tvg_id":channel.get("tvg_id"),"channel_name":channel.get("name"),"slug":channel.get("slug"),"vod_id":vod_id,"title":clean,"created_at":created_dt.astimezone(JST).isoformat() if created_dt else None,"ended_at":end_dt.astimezone(JST).isoformat() if end_dt else None,"duration_seconds":duration_s,"thumbnail":thumbnail if isinstance(thumbnail,str) else None,"replay_url":REPLAY_BASE+urllib.parse.quote(vod_id),"analysis_mode":mode,"chapter_status":"pending" if mode=="gmcx-ai" else "not_required"}
    item.update(parse_gmcx_range(clean) if mode=="gmcx-ai" else {})
    return item


def fetch_channel_vods(channel):
    slug=str(channel.get("slug") or "").strip()
    if not slug: return []
    candidates=[]
    for url in (f"https://kick.com/api/v2/channels/{urllib.parse.quote(slug)}/videos/latest", f"https://kick.com/api/v2/channels/{urllib.parse.quote(slug)}/videos"):
        payload=get_json(url)
        if payload is not None:
            candidates=extract_candidates(payload)
            if candidates: break
    out=[]
    for item in candidates[:MAX_VODS_PER_CHANNEL]:
        try: out.append(normalize_vod(item["vod_id"],item["raw"],channel))
        except Exception as exc: print(f"normalize failed {slug} {item.get('vod_id')}: {exc}")
    return out


def build_m3u(vods, config_by_id):
    lines=["#EXTM3U"]
    for item in vods:
        cfg=config_by_id.get(str(item.get("tvg_id"))) or {}; created=item.get("created_at") or "日時不明"
        try: created_label=datetime.fromisoformat(created).strftime("%m/%d %H:%M")
        except Exception: created_label=created
        title=item.get("title") or item.get("channel_name") or "KICK VOD"; display=f"📼 {item.get('channel_name')} {created_label} {title}"; logo=cfg.get("logo") or item.get("thumbnail") or ""; vod_id=item.get("vod_id"); tvg=f"{item.get('tvg_id')}.replay.{str(vod_id)[:12]}"
        lines.append(f'#EXTINF:-1 group-title="VOD" tvg-id="{tvg}" tvg-logo="{logo}",{display}')
        lines.append(str(item.get("replay_url")))
    return "\n".join(lines)+"\n"


def main():
    config=json.loads(CONFIG.read_text(encoding="utf-8-sig")); channels=[x for x in config if isinstance(x,dict) and x.get("tvg_id")]; all_vods=[]; status=[]
    for channel in channels:
        vods=fetch_channel_vods(channel); all_vods.extend(vods); status.append({"tvg_id":channel.get("tvg_id"),"name":channel.get("name"),"slug":channel.get("slug"),"vod_count":len(vods)}); print(channel.get("name"),"VODs:",len(vods))
    all_vods.sort(key=lambda x:x.get("created_at") or "",reverse=True); payload={"generated_at":datetime.now(JST).isoformat(),"resolver":REPLAY_BASE,"channels":status,"vods":all_vods}; OUT_JSON.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); OUT_M3U.write_text(build_m3u(all_vods,{str(x.get("tvg_id")):x for x in channels}),encoding="utf-8"); print(f"KICK VOD catalog: {len(all_vods)} VODs"); return 0

if __name__ == "__main__": raise SystemExit(main())
