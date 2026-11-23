# Kana Tube: single-writer ownership (2026-11-23)

## Contract

The ONLY authorized GitHub canonical publisher of Kana playback metadata is `youtube/manager.py` launched by `.github/workflows/update_youtube.yml` (`--scope special`).

It owns these three files:

- `youtube/output/kana.m3u`: official current YouTube **watch** URL (live or upcoming when confirmed).
- `youtube/output/kana_iptv.m3u`: short-lived upstream HLS candidate, **not** the stable FreeWiFi IPTV URL. It must not be regarded as playable after expiry or when real A/V segments are unavailable.
- `youtube/state/kana.json`: latest manager inspection status. An old state or failed inspection is not evidence of a current live broadcast.

`youtube/manager.py:sync_freewifi()` / `kana_managed_body()` are the one shared generator for the two FreeWiFi Kana entries. Public-sports/EPG writers may rebuild the aggregate `freewifi` file but **must** use the shared Kana body generator, and must not synthesize a YouTube-only block. They may not modify the three canonical Kana files above.

FreeWiFi must retain exactly two entries:

1. `youtube.kana_tube` = YouTube watch, or clearly unverified official live landing page if no prior watch exists.
2. `youtube.kana_tube_iptv` = fixed Railway `/kana-9x.m3u8` relay.

An unknown/offline/429/BOT_CHECK state must NOT delete both FreeWiFi entries or claim IPTV playback is working. On empty Kana output, the shared generator preserves a prior YouTube watch target marked **配信確認中** and retains the stable IPTV endpoint; it never claims HLS is good merely because the endpoint exists.

## Other components and their authority

- `.github/workflows/kana_iptv_altapi.yml`: independent **diagnostics only**, every 15 minutes during the defined hours. It can write only `youtube/state/kana_iptv_altapi.json`; it must not write canonical playlists, `kana.json`, or `freewifi`. Its candidate HLS is NOT currently promoted automatically into the canonical output.
- `.github/workflows/kana_instance_probe.yml`: manual read-only HLS chain diagnostics.
- Railway `freewifi-browser-bridge/kana-iptv-fresh`, source `kana_fresh_service/app.py`: runtime resolver and stable relay. Its resolver can independently discover an ID and read the canonical GitHub playlists; Railway does NOT write canonical GitHub files. A Railway deployment marked SUCCESS does NOT prove stream playback.
- `.github/workflows/update_public_sports_fast.yml` (10-minute) and `.github/workflows/update_freewifi_epg.yml` (hourly): may publish the aggregate FreeWiFi; currently call `freewifi_today_public_sports.py` and `finalize_today_public_sports.py`, which call `kana_managed_body()`.
- ChatGPT `華奈tube m3u8取得監視`: hourly supervision, NOT a separate direct playlist publisher; code changes must respect this single-writer contract.

## Deleted obsolete systems (2026-11-23)

- `.github/workflows/kana_iptv_v2.yml`
- `.github/workflows/kana_iptv_hls.yml`
- `.github/workflows/kana_iptv_fresh.yml`
- `.github/workflows/kana_iptv_rescue.yml`
- `.github/workflows/kana_iptv_fresh_publish.yml`
- `youtube/kana_iptv_resolver.py`
- `youtube/kana_iptv_v2.py`
- Orphaned `youtube/state/kana_iptv_v2.json`, `kana_iptv_probe.json`, and `kana_iptv_fresh.json`

All deletions remain recoverable through Git history. Do not restore independent writers without resolving ownership first.

## Success gates; known unresolved work

- Confirm current official channel **DAY and MID** IDs individually; prefer horizontal over vertical streams.
- Verify identical video ID across discovered LIVE state, selected HLS, and both published channels.
- Confirm URL validity, HLS child manifests, real video and audio segments, and `ffprobe` showing both streams.
- Recheck FreeWiFi YouTube watch slot and Railway IPTV slot; no success notice on an old archive, stale HLS, single-stream media, or deployment-health-only signal.
- Known at this consolidation: `kana.json` and `kana.m3u` have diverged; a public HLS was expired; Railway logged 429/502 and unavailable A/V. Consolidation itself does **not** fix upstream playback.
- Keep EPG, BOAT, keirin, KICK, and other functioning FreeWiFi channels untouched.
- Never use TinyFish.
