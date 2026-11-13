from __future__ import annotations
import json
from pathlib import Path

def visual_chapters(vod, clip_url):
    path = Path("gmcx_visual_cuts.json")
    if not path.exists():
        return None
    spec = json.loads(path.read_text(encoding="utf-8"))
    if str(vod.get("vod_id")) != spec["source_vod_id"] or vod.get("source_url") != spec["source_url"]:
        return None
    if not vod.get("playable") or not vod.get("ready_for_publish"):
        return None
    duration = int(spec["duration_seconds"])
    cuts = spec["cuts"]
    starts = [int(c["start_seconds"]) for c in cuts]
    if not starts or starts[0] != 0 or starts != sorted(set(starts)) or starts[-1] >= duration:
        raise ValueError("Invalid visual chapter boundaries")
    if abs(int(vod.get("duration_seconds") or 0) - duration) > 10:
        raise ValueError("Source duration changed; visual cuts require review")
    chapters = []
    for i, cut in enumerate(cuts):
        start = starts[i]
        stop = starts[i + 1] if i + 1 < len(cuts) else duration
        episode = cut.get("episode")
        chapter = dict(cut, kind="episode" if episode else "special",
                       stop_seconds=stop, duration_seconds=stop-start,
                       replay_url=clip_url(spec["source_vod_id"], start, stop-start),
                       method="king-room-visual-provisional", range_start=45)
        if not episode:
            chapter["special_key"] = f"visual-{spec['source_vod_id'][:8]}-{i}"
        chapters.append(chapter)
    return {"vod_id": spec["source_vod_id"], "source_title": vod.get("title"),
            "episode_start": 45, "episode_end": 59, "status": "ready",
            "duration_seconds": duration, "partial": True,
            "verification_status": "provisional_not_fully_verified",
            "notes": spec["notes"], "chapters": chapters}

