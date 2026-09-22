#!/usr/bin/env python3
from pathlib import Path

FREEWIFI = Path("freewifi")
PLAYLIST = Path("council/playlist.m3u")
IDS = ("ecatv.matsuyama_gikai", "ecatv.ehime_gikai")

def strip_ids(text):
    lines=text.splitlines()
    out=[]; i=0
    while i < len(lines):
        line=lines[i]
        if line.startswith("#EXTINF:") and any(f'tvg-id="{x}"' in line for x in IDS):
            i += 1
            while i < len(lines) and not lines[i].startswith("#EXTINF:") and not lines[i].startswith("## ") and not lines[i].startswith("# ==="):
                i += 1
            continue
        out.append(line); i += 1
    return "\n".join(out).rstrip()+"\n"

def payload():
    if not PLAYLIST.exists():
        return ""
    lines=PLAYLIST.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    return "\n".join(x for x in lines if not x.startswith("#EXTM3U") and x != "## 議会ライブ").strip()

def main():
    text=strip_ids(FREEWIFI.read_text(encoding="utf-8-sig", errors="replace"))
    p=payload()
    if p:
        anchor="## Rch"
        pos=text.find(anchor)
        if pos < 0:
            raise SystemExit("Rch boundary missing for council insertion")
        text=text[:pos].rstrip()+"\n\n"+p+"\n\n"+text[pos:]
    FREEWIFI.write_text(text.rstrip()+"\n", encoding="utf-8")
    print("council projection synced")

if __name__=="__main__":
    main()
