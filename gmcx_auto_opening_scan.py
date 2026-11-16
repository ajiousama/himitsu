#!/usr/bin/env python3
"""Hourly GCCX audio-based provisional splitting on *new* KICK archive recordings.

Learn the recurring GCCX opening sound from multiple live-archive examples
once; keep a compact spectral fingerprint so later VOD expiration does not
destroy the template. Scan previously unexamined clips of newest playable VODs.

This does NOT store music/audio, detect game titles from sound, or rewrite
confirmed video boundaries. VOD5 uses only conservative provisional candidates.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
import numpy as np

from gmcx_auto_cut_audio import (
    SAMPLE_RATE,HOP,TEMPLATE_OFFSETS,TEMPLATE_SECONDS,
    candidate_matches,consensus,fingerprint
)
from gmcx_long_nav import _range_for_vod,time_slices

REPLAY=Path("kick_replay.json")
CHAPTERS=Path("kick_gmcx_chapters.json")
REPORT=Path("gmcx_auto_opening_review.json")
REFERENCE=Path("gmcx_opening_fingerprint.json")
RESOLVER="https://kick-resolver-production.up.railway.app/kick"
JST=timezone(timedelta(hours=9))
WINDOW_BEFORE=52
WINDOW_LENGTH=126
REFERENCE_LENGTH=75
WINDOW_TIMEOUT=20
MIN_REFERENCE_CORROBORATIONS=2
# For a 58m navigation edge the audio motif is sometimes 28s earlier.
MAX_ACCEPTED_SHIFT=36
MAX_NEW_CUTS_PER_RUN=20
MIN_STRONG_MATCHES=2
MIN_SCORE=.68
RETRY_AFTER_HOURS=6
REFERENCE_SEED_SECONDS=(3480,6960,10440,13920,17400,20880,24360)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def extract(url: str, seek: int, length: int) -> np.ndarray | None:
    cmd=[
        "ffmpeg","-nostdin","-hide_banner","-loglevel","error",
        "-rw_timeout","8000000","-ss",str(seek),"-i",url,
        "-t",str(length),"-vn","-ac","1","-ar",str(SAMPLE_RATE),
        "-f","f32le","pipe:1",
    ]
    try:
        p=subprocess.run(cmd,capture_output=True,timeout=WINDOW_TIMEOUT,check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if p.returncode:
        return None
    signal=np.frombuffer(p.stdout,dtype="<f4")
    return signal if signal.size >= SAMPLE_RATE*min(25,length-2) else None


def audio(vod:dict,start:int,length:int) -> tuple[np.ndarray|None,str]:
    signal=extract(str(vod["source_url"]),start,length)
    if signal is not None:
        return signal,"source"
    url=(f"{RESOLVER}?vod={quote(str(vod['vod_id']),safe='')}"
         f"&start={start}&duration={length}")
    signal=extract(url,0,length)
    if signal is not None:
        return signal,"resolver"
    return None,"unavailable"


def parse_data():
    replay=json.loads(REPLAY.read_text(encoding="utf-8"))
    chapters=json.loads(CHAPTERS.read_text(encoding="utf-8"))
    by_id={str(g.get("vod_id")):g for g in chapters.get("results",[])
           if isinstance(g,dict)}
    vods=[
        v for v in replay.get("vods",[])
        if isinstance(v,dict)
        and str(v.get("tvg_id") or "").startswith("kick.gccx")
        and v.get("playable") is True and v.get("ready_for_publish") is True
        and int(v.get("duration_seconds") or 0)>=7200
        and v.get("source_url") and v.get("vod_id") in by_id
    ]
    vods.sort(key=lambda v:str(v.get("created_at") or ""),reverse=True)
    return vods,by_id


def build_cache(fp:np.ndarray, source:dict, seed:int,
                agreement:int, now:datetime) -> dict:
    length=TEMPLATE_SECONDS*SAMPLE_RATE//HOP
    templates=[]
    for offset in TEMPLATE_OFFSETS:
        start=offset*SAMPLE_RATE//HOP
        chunk=fp[start:start+length]
        if chunk.shape!=(length,32):
            raise ValueError("Unexpected audio fingerprint template shape")
        templates.append(np.round(chunk,3).tolist())
    return {
        "schema_version":1,
        "algorithm":"gmcx_auto_cut_audio.fingerprint and consensus",
        "created_utc":now.isoformat(),
        "seed_vod_id":source["vod_id"],
        "seed_source_url":source["source_url"],
        "seed_seconds":seed,
        "corroborating_distinct_start_windows":agreement,
        "hop":HOP,
        "sample_rate":SAMPLE_RATE,
        "template_offsets_seconds":list(TEMPLATE_OFFSETS),
        "template_duration_seconds":TEMPLATE_SECONDS,
        "templates":templates,
        "warning":"Derived non-playable spectral features only, not song samples. Matches are provisional."
    }


def cache_to_anchor(cache:dict) -> np.ndarray:
    if (cache.get("schema_version")!=1
        or cache.get("corroborating_distinct_start_windows",0)<MIN_REFERENCE_CORROBORATIONS
        or cache.get("template_offsets_seconds")!=list(TEMPLATE_OFFSETS)
        or cache.get("template_duration_seconds")!=TEMPLATE_SECONDS
        or cache.get("hop")!=HOP or cache.get("sample_rate")!=SAMPLE_RATE):
        raise ValueError("Unverified GCCX opening template")
    size=(max(TEMPLATE_OFFSETS)+TEMPLATE_SECONDS)*SAMPLE_RATE//HOP
    anchor=np.zeros((size,32),dtype=np.float32)
    win=TEMPLATE_SECONDS*SAMPLE_RATE//HOP
    if len(cache.get("templates",[]))!=len(TEMPLATE_OFFSETS):
        raise ValueError("Wrong number of GCCX motif templates")
    for at,values in zip(TEMPLATE_OFFSETS,cache["templates"]):
        arr=np.asarray(values,dtype=np.float32)
        if arr.shape!=(win,32) or not np.isfinite(arr).all():
            raise ValueError("Corrupt GCCX motif fingerprint")
        start=at*SAMPLE_RATE//HOP
        anchor[start:start+win]=arr
    return anchor


def bootstrap(vods:list[dict],deadline:float) -> tuple[np.ndarray|None,dict|None]:
    # Favor a recording already known to contain several regular openers.
    ordered=sorted(vods,key=lambda v:(
        not str(v.get("vod_id","")).startswith("e4f91158"),
        not str(v.get("vod_id","")).startswith("df1386fd"),
        str(v.get("created_at") or "")))
    for vod in ordered:
        if time.monotonic()>deadline-70:
            break
        examples={}
        for t in REFERENCE_SEED_SECONDS:
            if time.monotonic()>deadline-50 or t+REFERENCE_LENGTH>int(vod["duration_seconds"]):
                break
            audio_buf,method=audio(vod,t,REFERENCE_LENGTH)
            if audio_buf is not None:
                examples[t]=fingerprint(audio_buf)
            if len(examples)>=5:
                break
        if len(examples)<3:
            continue
        scored=[]
        for t,fp in examples.items():
            votes=0
            for second in examples:
                if second==t or time.monotonic()>deadline-20:
                    continue
                signal,_=audio(vod,second-WINDOW_BEFORE,WINDOW_LENGTH)
                if signal is None:
                    continue
                outcome=consensus(candidate_matches(fp,fingerprint(signal)))
                if (outcome.get("status")=="candidate"
                    and outcome.get("strong_matches",0)>=MIN_STRONG_MATCHES
                    and outcome.get("mean_similarity",0)>=MIN_SCORE):
                    votes+=1
            scored.append((votes,t))
            print("GCCX_REF_TRIAL",vod["vod_id"][:8],t,votes,flush=True)
            if votes>=MIN_REFERENCE_CORROBORATIONS:
                return fp,build_cache(fp,vod,t,votes,utc_now())
    return None,None


def load_state() -> dict:
    try:
        report=json.loads(REPORT.read_text(encoding="utf-8"))
        if report.get("schema_version")==1 and isinstance(report.get("vods"),dict):
            return report
    except (OSError,ValueError):
        pass
    return {"schema_version":1,"description":"Automatic audio candidate starts, NOT verified episode boundaries.",
            "vods":{}}


def eligible(vods:list[dict],groups:dict,state:dict,now:datetime):
    for vod in vods:
        unknown=_range_for_vod(vod,groups[vod["vod_id"]])
        if unknown is None:
            continue
        start,end,_=unknown
        spans=time_slices(start,end)
        prev=state["vods"].get(vod["vod_id"],{})
        saved_rows=(prev.get("rows") or {}) if (
            prev.get("source_url")==vod.get("source_url")
            and prev.get("duration_seconds")==vod.get("duration_seconds")) else {}
        # Newest source first. Preserve previously attempted sections until
        # the 6-hour retry cooldown has elapsed.
        for a,b in spans[1:]:
            if a<WINDOW_BEFORE or a+WINDOW_LENGTH>=int(vod["duration_seconds"]):
                continue
            row=saved_rows.get(str(a),{})
            if row.get("status") in ("candidate","insufficient"):
                continue
            if row.get("status")=="decode_failed":
                try:
                    previous=datetime.fromisoformat(row.get("last_attempt_utc"))
                    if now-previous<timedelta(hours=RETRY_AFTER_HOURS):
                        continue
                except (TypeError,ValueError):
                    pass
            yield vod,start,end,a,b


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--budget-seconds",type=int,default=420)
    parser.add_argument("--max-new",type=int,default=MAX_NEW_CUTS_PER_RUN)
    args=parser.parse_args()
    deadline=time.monotonic()+max(60,min(720,args.budget_seconds))
    now=utc_now()
    vods,groups=parse_data()
    if not vods:
        print("GCCX_AUTO_OPENING_NO_PLAYABLE_RECORDINGS",flush=True)
        return 0
    if REFERENCE.is_file():
        cache=json.loads(REFERENCE.read_text(encoding="utf-8"))
        anchor=cache_to_anchor(cache)
        print("GCCX_AUTO_OPENING_REFERENCE_CACHED",cache["seed_vod_id"][:8],flush=True)
    else:
        anchor,cache=bootstrap(vods,deadline)
        if anchor is None or cache is None:
            print("::warning::No reproducible GCCX audio reference; no boundaries modified",flush=True)
            return 0
        REFERENCE.write_text(json.dumps(cache,ensure_ascii=False,separators=(",",":"))+"\n",
                             encoding="utf-8")
        print("GCCX_AUTO_OPENING_REFERENCE_CREATED",cache["seed_vod_id"][:8],flush=True)
    state=load_state()
    done=0
    for vod,begin,end,nominal,stop in eligible(vods,groups,state,now):
        if done>=args.max_new or time.monotonic()>deadline-42:
            break
        audio_buf,method=audio(vod,nominal-WINDOW_BEFORE,WINDOW_LENGTH)
        row={"status":"decode_failed","last_attempt_utc":utc_now().isoformat(),
             "method":method,"verification":"audio_only_needs_video"}
        if audio_buf is not None:
            try:
                found=consensus(candidate_matches(anchor,fingerprint(audio_buf)))
                if found.get("status")=="candidate":
                    shift=float(found.get("shift_seconds") or 0)
                    matches=int(found.get("strong_matches") or 0)
                    similarity=float(found.get("mean_similarity") or 0)
                    if (abs(shift)<=MAX_ACCEPTED_SHIFT
                        and matches>=MIN_STRONG_MATCHES
                        and similarity>=MIN_SCORE):
                        row.update(status="candidate",
                                   candidate_seconds=round(nominal+shift,1),
                                   strong_matches=matches,
                                   mean_similarity=similarity)
                    else:
                        row.update(status="insufficient")
                else:
                    row.update(status="insufficient")
            except (ValueError,TypeError) as exc:
                row.update(status="fingerprint_failed",reason=str(exc)[:130])
        entry=state["vods"].setdefault(vod["vod_id"],{
            "source_url":vod["source_url"],"duration_seconds":vod["duration_seconds"],
            "created_at":vod.get("created_at"),"rows":{},
        })
        if (entry.get("source_url")!=vod["source_url"]
            or entry.get("duration_seconds")!=vod["duration_seconds"]):
            entry.update(source_url=vod["source_url"],
                         duration_seconds=vod["duration_seconds"],rows={})
        entry["rows"][str(nominal)]=row
        done+=1
        print("GCCX_AUTO_OPENING",vod["vod_id"][:8],nominal,
              row["status"],row.get("candidate_seconds"),method,flush=True)
    if done:
        state["updated_utc"]=utc_now().isoformat()
        state["reference_seed_id"]=cache["seed_vod_id"]
        REPORT.write_text(json.dumps(state,ensure_ascii=False,indent=2)+"\n",
                          encoding="utf-8")
    print("GCCX_AUTO_OPENING_FINISHED",done,"new checks",flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
