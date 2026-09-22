# haru system

Standalone HARU replay/VOD subsystem.

- `haru_vod.py` builds the VOD playlist from generated replay EPG history
- `haru_vod_clips.py` creates bounded clips through the HARU clip resolver
- `build_haru_kai_epg.py` maintains rolling replay metadata/history
- `haru_vod.m3u` is the subsystem output
- root `haru_vod.m3u` remains a compatibility mirror because the public Vercel redirect already points there

HARU remains isolated from the canonical `tv/` live-source system.
