# youtube system

Canonical YouTube live-camera system for FreeWiFi.

- `config.json`: source definitions
- `output/general.m3u`: resolved general live cameras
- `output/kana.m3u`: Kana live/upcoming slot
- `output/mandarin.m3u`: Ehime Mandarin Pirates live output
- `manager.py`: resolver and FreeWiFi projection logic

`freewifi` is the aggregate output; YouTube source state lives here.

## KanaTube publication ownership

See [KANA_UPDATE_OWNERSHIP.md](KANA_UPDATE_OWNERSHIP.md) before changing any Kana resolver or scheduled job. Only `manager.py` through `update_youtube.yml` may publish canonical Kana output/state. The Alt API and Instance Probe are diagnostics, Railway is the IPTV relay, and public-sports writers must preserve the two shared FreeWiFi entries. Do not recreate the retired direct writers.
