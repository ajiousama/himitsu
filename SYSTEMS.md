# FreeWiFi update systems

FreeWiFi is the aggregate output. Update ownership is split into five systems:

1. **ganble/** — public sports / today's venues
   - canonical master: `ganble/playlist.m3u`
2. **youtube/** — YouTube live cameras and Kana/Mandarin
   - canonical config/output under `youtube/`
3. **radio/** — NHK / Radiko / community radio
   - canonical catalog: `radio/playlist.m3u`
   - FreeWiFi projection: `radio/freewifi.m3u`
4. **vod5/** — KICK live/replay/VOD
   - canonical VOD catalog: `vod5/playlist.m3u`
   - FreeWiFi projections: `vod5/freewifi_live.m3u`, `vod5/freewifi_specials.m3u`
5. **ehime_catv/** — Ehime CATV channels
   - canonical playlist: `ehime_catv/playlist.m3u`

6. **rakuten/** — Rakuten Rch channels and Rakuten EPG helpers
7. **tv/** — terrestrial / BS / Green Channel / CS source system
8. **tver/** — standalone TVer realtime/news streams
9. **epg/** — common EPG build and final audit system
10. **logos/** — shared logo assets, generators and contrast normalization

The root `freewifi` file remains the user-facing aggregate playlist.
The root `guides.xml` remains the user-facing EPG compatibility output.

Compatibility:
- root `radio.m3u` is a generated compatibility mirror
- root `VOD5` is a generated compatibility mirror
- the old root `ganble` file has been replaced by the `ganble/` system directory
