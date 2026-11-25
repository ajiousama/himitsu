"""Canonical final public-sports projection. Run on latest main before committing.
Acquisition workers retain their own cadence; no worker publishes an independently
formatted race grid. Never change TV/YouTube/VOD or BOAT playback availability.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, time
from pathlib import Path
import argparse
import json
import re
import xml.etree.ElementTree as ET
from normalize_race_epg_switch import normalize_root, validate_root, is_target, fmt, parse_xmltv
from sports_race_time import JST, race_time

LOCAL = Path("public_sports_epg_local.xml")
GUIDES = Path("guides.xml")
VERIFIED = Path("verified_daily_status.json")
VENUES = ("keirin.", "chihou.", "auto.", "boat.")
NONBOAT = ("keirin.", "chihou.", "auto.")
CANCEL = ("中止", "開催予定に変更", "順延")
MODES = {"morning":"モーニング","day":"デイ","twilight":"薄暮","night":"ナイター",
         "midnight":"ミッドナイト","overnight":"オーバーミッドナイト"}

def cid_of(el):
    return el.get("id", "") if el.tag == "channel" else el.get("channel", "") if el.tag == "programme" else ""

def title(p):
    return p.findtext("title") or ""

def group_day(p):
    r = race_time(p)
    if r:
        return r["day"]
    start = parse_xmltv(p.get("start"))
    return start.date() if start else None

def race_keys(rows):
    return {(r["race"], r["dt"]) for p in rows if (r := race_time(p))}

def write(root, path):
    channels = [p for p in root if p.tag == "channel"]
    other = [p for p in root if p.tag not in ("programme", "channel")]
    progs = sorted(root.findall("programme"), key=lambda p: (p.get("start",""),p.get("channel","")))
    root[:] = channels + other + progs
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)

def groups(root, day):
    out = defaultdict(list)
    for p in root.findall("programme"):
        if group_day(p) == day:
            out[cid_of(p)].append(p)
    return out

def merge_fresh(old, fresh, day):
    """Retain same-day successful non-BOAT cards if new acquisition is partial.
    Explicit cancellation wins. Never promote yesterday's rows to today.
    BOAT worker is the authoritative source for its current-day rows.
    """
    old_groups, new_groups = groups(old, day), groups(fresh, day)
    old_channels = {cid_of(p):p for p in old.findall("channel")}
    fresh_channels = {cid_of(p) for p in fresh.findall("channel")}
    for cid, rows in old_groups.items():
        incoming = new_groups.get(cid, [])
        if cid.startswith("boat."):
            use_old = bool(rows)
        elif is_target(cid):
            use_old = (len(race_keys(rows)) > len(race_keys(incoming))
                       and not any(any(x in title(p) for x in CANCEL) for p in incoming))
        else:
            use_old = False
        if not use_old:
            continue
        for p in incoming:
            fresh.remove(p)
        for p in rows:
            fresh.append(deepcopy(p))
        if cid not in fresh_channels and cid in old_channels:
            fresh.insert(0, deepcopy(old_channels[cid]))
            fresh_channels.add(cid)
        print("Retained current-day card", cid, len(race_keys(rows)))
    return fresh

def load_status():
    return json.loads(VERIFIED.read_text(encoding="utf-8-sig"))

def merge_files(fresh_path, verified_path):
    now = datetime.now(JST)
    new_status = json.loads(verified_path.read_text(encoding="utf-8-sig"))
    if new_status.get("date") != now.date().isoformat():
        raise RuntimeError("stale acquisition snapshot")
    old_status = load_status() if VERIFIED.exists() else {}
    fresh = ET.parse(fresh_path).getroot()
    if LOCAL.exists() and LOCAL.stat().st_size:
        old = ET.parse(LOCAL).getroot()
        fresh = merge_fresh(old, fresh, now.date())
    # Recover verified venue metadata only for retained actual current-day cards.
    if old_status.get("date") == now.date().isoformat():
        from epg.keirin_epg_direct import KEIRIN_IDS
        from epg.keiba_epg_direct import TVG_IDS
        from epg.autorace_epg_direct import AUTO
        mappings = {"競輪": KEIRIN_IDS, "地方競馬": TVG_IDS,
                    "オートレース": {k:v[0] for k,v in AUTO.items()}}
        by_cid = groups(fresh, now.date())
        for sport, mapping in mappings.items():
            for name in old_status.get("public_sports", {}).get(sport, []):
                rows = by_cid.get(mapping.get(name), [])
                if not race_keys(rows) or any(any(x in title(p) for x in CANCEL) for p in rows):
                    continue
                dest = new_status.setdefault("public_sports", {}).setdefault(sport, [])
                if name not in dest:
                    dest.append(name)
                mode = old_status.get("public_sports_modes", {}).get(sport, {}).get(name)
                if mode:
                    new_status.setdefault("public_sports_modes", {}).setdefault(sport, {}).setdefault(name,mode)
        for cid in old_status.get("jra_active_ids", []):
            if race_keys(by_cid.get(cid, [])) and cid not in new_status.setdefault("jra_active_ids", []):
                new_status["jra_active_ids"].append(cid)
    write(fresh, LOCAL)
    VERIFIED.write_text(json.dumps(new_status, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

def prepare(root, day):
    """Turn confirmed provisional schedules into honest all-day waiting guides."""
    start = datetime.combine(day, time(0), JST)
    end = start + timedelta(days=1)
    by_cid = groups(root, day)
    for cid, rows in by_cid.items():
        if not cid.startswith(VENUES):
            continue
        if race_keys(rows) or any(any(x in title(p) for x in CANCEL) for p in rows):
            continue
        official = [p for p in rows if "開催予定" in title(p) and
                    any(x in (p.findtext("desc") or "") for x in ("公式開催表", "公式出走表"))]
        if not official:
            continue
        name = next((c.findtext("display-name") for c in root.findall("channel") if cid_of(c)==cid), cid)
        for p in rows:
            root.remove(p)
        p = ET.SubElement(root,"programme",channel=cid,start=fmt(start),stop=fmt(end))
        ET.SubElement(p,"title",lang="ja").text = f"本日{name}開催　発走時刻取得待ち"
        ET.SubElement(p,"desc",lang="ja").text = "公式開催日程で開催確認済み。発走時刻は未取得です。"
    normalize_root(root)
    validate_root(root,"canonical public sports")
    return root

def project(local, guides):
    """Replace only race venue channels. Preserve all other guide entries."""
    # Keep previous days in guides; replace today/future using canonical source.
    today = datetime.now(JST).date()
    authoritative = {cid_of(p) for p in local.findall("channel") if cid_of(p).startswith(VENUES)}
    existing = {cid_of(p) for p in guides.findall("channel")}
    for p in list(guides.findall("programme")):
        if cid_of(p).startswith(VENUES) and (d := group_day(p)) is not None and d >= today:
            guides.remove(p)
    for p in local.findall("channel"):
        cid = cid_of(p)
        if cid in authoritative and cid not in existing:
            guides.insert(0,deepcopy(p))
            existing.add(cid)
    for p in local.findall("programme"):
        if cid_of(p) in authoritative and (d := group_day(p)) is not None and d >= today:
            guides.append(deepcopy(p))

def validate_visible(local, guides, playlist, day):
    ids = []
    for line in playlist.splitlines():
        if not line.startswith("#EXTINF:") or 'group-title="今日の開催場"' not in line:
            continue
        m = re.search(r'tvg-id="([^"]+)"',line)
        if m and m.group(1).startswith(VENUES):
            ids.append(m.group(1))
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate sports playlist IDs")
    lg, gg = groups(local, day), groups(guides, day)
    errors = []
    for cid in ids:
        a, b = lg.get(cid,[]),gg.get(cid,[])
        sig = lambda rows: sorted((p.get("start"),p.get("stop"),title(p)) for p in rows)
        if not a or sig(a) != sig(b):
            errors.append(cid)
    if errors:
        raise RuntimeError("playlist/EPG mismatch: "+", ".join(errors))
    print("Canonical public sports consistency OK", day, "visible venues",len(ids))

def publish():
    local = prepare(ET.parse(LOCAL).getroot(),datetime.now(JST).date())
    guides = ET.parse(GUIDES).getroot()
    project(local,guides)
    # JRA regional HQ/LQ projection is made by jra_epg_merge before this gate;
    # its race boundaries are normalized here without touching normal GCH TV.
    normalize_root(guides)
    validate_root(guides,"canonical guides")
    validate_visible(local,guides,Path("freewifi").read_text(encoding="utf-8-sig"),datetime.now(JST).date())
    write(local,LOCAL)
    write(guides,GUIDES)

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--merge-fresh",nargs=2,type=Path)
    args=p.parse_args()
    if args.merge_fresh:
        merge_files(*args.merge_fresh)
    else:
        publish()
