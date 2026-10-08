#!/usr/bin/env python3
"""Read-only HARUKA HLS transition fingerprints. No change to live playlists."""
import datetime as dt
import hashlib
import json
import subprocess
import tempfile
import urllib.request
from urllib.parse import urljoin, urlparse

BASE = "http://118.69.27.222:9394"
CHANNELS = {"ABC": "28", "TVO": "22"}
def get_bytes(url, limit=1500000):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as r:
        data = r.read(limit + 1)
        if len(data) > limit: raise ValueError("size limit")
        return data

def playlist(name, no):
    url = f"{BASE}/stream/{no}.m3u8"
    lines = get_bytes(url, 250000).decode("utf-8", "replace").splitlines()
    segments, pending, marker = [], None, False
    for line in lines:
        line = line.strip()
        if line.startswith("#EXT-X-DISCONTINUITY") and line == "#EXT-X-DISCONTINUITY":
            marker = True
        elif line.startswith("#EXTINF:"):
            try: pending = float(line.split(":", 1)[1].split(",")[0])
            except ValueError: pending = None
        elif line and not line.startswith("#"):
            segments.append((urljoin(url, line), pending, marker))
            pending, marker = None, False
    return segments

def fingerprint(url):
    if urlparse(url).hostname != urlparse(BASE).hostname:
        return {"error": "different host"}
    raw = get_bytes(url, limit=16000000)
    with tempfile.NamedTemporaryFile(suffix=".ts") as f:
        f.write(raw);f.flush()
        cmd = ["ffmpeg","-nostdin","-v","error","-i",f.name,"-vf","scale=16:16,format=gray","-frames:v","1","-f","rawvideo","-"]
        p = subprocess.run(cmd, capture_output=True, timeout=12)
        if p.returncode != 0 or len(p.stdout)!=256:
            return {"size":len(raw),"error":"frame unavailable"}
        # Perceptual fingerprint: grayscale pixels; truncated to avoid media redistribution
        pixels = p.stdout
        avg = sum(pixels)/len(pixels)
        bits = "".join("1" if v >= avg else "0" for v in pixels)
        return {"size":len(raw), "frame_ahash":f"{int(bits,2):064x}"}

def main():
    results=[]
    for name, no in CHANNELS.items():
        try:
            segs=playlist(name,no)
            for idx,(url, duration, discontinuity) in enumerate(segs):
                if not discontinuity:continue
                sample=[]
                for j in range(max(0,idx-2),min(len(segs),idx+3)):
                    uri,dur,mark=segs[j]
                    try: sig=fingerprint(uri)
                    except Exception as e: sig={"error":type(e).__name__}
                    sample.append({"relative":j-idx,"duration":dur,"marker":mark,**sig})
                results.append({"channel":name,"timestamp_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"transition_samples":sample})
        except Exception as e:
            results.append({"channel":name,"error":type(e).__name__})
    print(json.dumps(results,ensure_ascii=False))
if __name__=="__main__":main()
