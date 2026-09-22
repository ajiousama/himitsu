# services system

Runtime resolver/proxy services used by playlists and apps.

Canonical implementations:
- `kick/` — KICK live/VOD resolver handlers
- `tver/` — TVer resolver
- `haru/` — HARU clip resolver
- `iptv-proxy/` — browser/HLS proxy
- `ehime-catv/` — Ehime CATV DASH-to-HLS bridge
- `jun-iptv/` — APK redirect handler

Compatibility contract:
- public Vercel routes remain under root `api/`
- root `api/*.js` files are thin compatibility entrypoints
- existing M3U/APTV URLs therefore do not change

Deploy-root projects `vercel-radiko/` and `standalone-radio-tv/` keep their physical roots because their deployment configuration depends on those paths; they are logically part of this services layer.
