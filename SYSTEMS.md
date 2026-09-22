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

The root `freewifi` file remains the user-facing aggregate playlist.

Compatibility:
- root `radio.m3u` is a generated compatibility mirror
- root `VOD5` is a generated compatibility mirror
- the old root `ganble` file has been replaced by the `ganble/` system directory
