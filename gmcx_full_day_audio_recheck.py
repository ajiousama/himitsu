#!/usr/bin/env python3
"""Recheck EVERY available GCCX recording-day audio boundary, without publishing guesses.

One probe per existing cut (normal episodes AND long time-navigation entries).
Match recurrent opening music using the independently repeated November 9
source cue. A music match is only a time *candidate*, not episode proof.
A failed decode is NOT evidence that the opening didn't happen.

GitHub Actions shards by recording and cut index. Fixed-source and bounded HLS
decode, with a clipped Railway resolver fallback to avoid >2 minute hangs.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np
from gmcx_auto_cut_audio import fingerprint, candidate_matches, consensus, SAMPLE_RATE

VOD5 = Path("vod5/playlist.m3u")
REPLAY = Path("kick_replay.json")
PREVIOUS = Path("gmcx_audio_opener_findings_20261116.json")
SEED_ID = "df1386fd-4bd1-41ae-ac64-743ff49a838f"
SEED_START = 3487
SEED_LENGTH = 75
BEFORE = 52
DURATION = 126
TIMEOUT_SECONDS = 23
RESOLVER = "https://kick-resolver-production.up.railway.app/kick"
OUTDIR = Path("gmcx_full_day_audio_review")


def archived_vods() -> dict:
    data = json.loads(REPLAY.read_text(encoding="utf-8"))
    return {
        row["vod_id"]: row for row in data.get("vods", [])
        if str(row.get("tvg_id") or "").startswith("kick.gccx")
        and row.get("playable") is True
        and row.get("ready_for_publish") is True
        and int(row.get("duration_seconds") or 0) > 0
        and row.get("source_url")
    }


def playlist_items() -> list[dict]:
    lines = VOD5.read_text(encoding="utf-8-sig").splitlines()
    if not lines or not lines[0].startswith("#EXTM3U"):
        raise ValueError("Invalid published VOD5")
    items = []
    for idx in range(1, len(lines)-1, 2):
        name, url = lines[idx], lines[idx+1]
        if not name.startswith("#EXTINF:"):
            raise ValueError("VOD5 malformed at line "+str(idx+1))
        query = parse_qs(urlsplit(url).query)
        if "vod" not in query or "start" not in query:
            continue
        tvg = re.search(r'tvg-id="([^"]+)"', name)
        if not tvg or not tvg.group(1).startswith(("kick.gmcx.", "kick.gccx2.")):
            continue
        try:
            items.append({
                "vod_id": query["vod"][0],
                "nominal": int(query["start"][0]),
                "clip_length": int(query.get("duration",["0"])[0]),
                "id": tvg.group(1),
                "caption": name.split(",",1)[-1],
            })
        except (TypeError, ValueError):
            continue
    # A programme opening preview duplicates a normal time-navigation slice.
    dedup = {}
    for row in items:
        key=(row["vod_id"], row["nominal"])
        if key not in dedup or (".nav." in row["id"] and ".nav." not in dedup[key]["id"]):
            dedup[key]=row
    return sorted(dedup.values(), key=lambda x:(x["vod_id"],x["nominal"]))


def extract(url: str, seek: float, seconds: int, timeout=TIMEOUT_SECONDS):
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel","error",
        "-rw_timeout",str(9_000_000), "-ss",f"{seek:.1f}","-i",url,
        "-t",str(seconds),"-vn","-ac","1","-ar",str(SAMPLE_RATE),
        "-f","f32le","pipe:1",
    ]
    try:
        result = subprocess.run(cmd,capture_output=True,timeout=timeout,check=False)
    except (subprocess.TimeoutExpired,OSError) as exc:
        return None,"timeout_or_exec:"+str(exc)[:120]
    data=np.frombuffer(result.stdout,dtype="<f4")
    if data.size < SAMPLE_RATE*25:
        return None,("error:"+result.stderr.decode("utf-8","replace")[-120:]
                     if result.returncode else "too_few_audio_samples")
    return data,None


def bounded_audio(vod: dict, start: int, length: int):
    # Direct HLS seek: cheap when available, not reliable for hour 30 onwards.
    buf,error=extract(vod["source_url"],start,length)
    if buf is not None:
        return buf,"source",None
    # Railway resolver URL is a bounded slice, NOT a seek into a 48h master.
    clip=f"{RESOLVER}?vod={vod['vod_id']}&start={start}&duration={length}"
    buf,backup_error=extract(clip,0,length)
    if buf is not None:
        return buf,"resolver",None
    return None,"unavailable",f"source:{error}; resolver:{backup_error}"


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--vod-prefix",required=True)
    parser.add_argument("--shard",type=int,required=True)
    parser.add_argument("--shards",type=int,default=3)
    args=parser.parse_args()
    if not 0<=args.shard<args.shards or args.shards>12:
        parser.error("invalid shard")
    vods=archived_vods()
    selected=[v for ident,v in vods.items() if ident.startswith(args.vod_prefix)]
    if len(selected)!=1:
        raise RuntimeError("Expected one active GCCX VOD: "+args.vod_prefix)
    vod=selected[0]
    record_date=str(vod.get("created_at") or "")[:10]
    all_items=[x for x in playlist_items() if x["vod_id"]==vod["vod_id"]]
    if not all_items:
        raise RuntimeError("No candidate recording cuts: "+args.vod_prefix)
    items=[x for i,x in enumerate(all_items) if i%args.shards==args.shard]
    if not items:
        raise RuntimeError("No items in requested shard")
    prev=json.loads(PREVIOUS.read_text(encoding="utf-8"))
    if (prev["source_action_run"] != 43767291966
            or prev["reference"]["source_start_seconds"]!=SEED_START
            or prev["reference"]["corroborated_other_openers"]<4):
        raise RuntimeError("Audio reference is not independently corroborated")
    source=vods.get(SEED_ID)
    if not source:
        raise RuntimeError("Prior sound reference source no longer available")
    anchor,method,reason=bounded_audio(source,SEED_START,SEED_LENGTH)
    if anchor is None:
        raise RuntimeError("Opening reference unavailable: "+str(reason))
    anchor_fp=fingerprint(anchor)
    dest=OUTDIR/f"{args.vod_prefix}_{args.shard:02d}_of_{args.shards:02d}.json"
    OUTDIR.mkdir(parents=True,exist_ok=True)
    result={
        "schema_version":1,
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "date":record_date,"vod_id":vod["vod_id"],
        "source_duration_seconds":int(vod["duration_seconds"]),
        "shard":args.shard,"shards":args.shards,
        "total_recording_cut_candidates":len(all_items),
        "tested_in_shard":len(items),
        "reference":{"vod_id":SEED_ID,"seconds":SEED_START,
                     "corroboration_count":prev["reference"]["corroborated_other_openers"],
                     "decoded_from":method},
        "production_changed":False,
        "interpretation":"Audio candidates ONLY. No programme or title boundaries confirmed; fails are untested.",
        "rows":[],
    }
    print("GCCX_ALL_DAYS",record_date,vod["vod_id"],
          "parts",len(all_items),"shard",args.shard,"of",args.shards,flush=True)
    for item in items:
        row={k:item[k] for k in ("id","nominal","clip_length","caption")}
        row["status"]="not_testable"
        if item["nominal"]<BEFORE or item["nominal"]+100>=int(vod["duration_seconds"]):
            row["reason"]="near_source_edge"
        else:
            signal,kind,error=bounded_audio(vod,int(item["nominal"])-BEFORE,DURATION)
            row["media_read_mode"]=kind
            if signal is None:
                row.update(status="decode_failed",reason=error)
            else:
                try:
                    raw=candidate_matches(anchor_fp,fingerprint(signal))
                    outcome=consensus(raw)
                    row.update(outcome)
                    if outcome.get("status")=="candidate":
                        row["audio_candidate_start_seconds"]=round(
                            float(item["nominal"])+float(outcome["shift_seconds"]),1)
                        row["delta_from_provisional_seconds"]=round(
                            float(outcome["shift_seconds"]),1)
                        row["requires_video_and_title_verification"]=True
                except Exception as exc:
                    row.update(status="fingerprint_failed",reason=str(exc)[:180])
        result["rows"].append(row)
        status=row["status"]
        print("GCCX_DAY_CUT",record_date,args.vod_prefix,item["nominal"],
              status,row.get("audio_candidate_start_seconds"),
              row.get("media_read_mode","none"),flush=True)
        # Persist partial results for any timed-out job.
        result["summary"]=dict(Counter(x["status"] for x in result["rows"]))
        dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("GCCX_DAY_COMPLETE",record_date,args.shard,result["summary"],flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
