# radiko backup plan

## Purpose

Keep the working VPN Gate region-probe mechanism as a recovery/diagnostic path for the radiko IPTV proxy.

## Normal operation

- radiko Premium authentication remains the normal and required path for area-free listening.
- `radiko_proxy.py` serves the local VLC playlist/proxy on port 9395.
- VPN Gate is not required when the normal network path is healthy.

## Backup / recovery operation

If the normal network path has connectivity, routing, geo-detection, or repeated HTTP transport problems:

1. Keep the Premium credentials/authentication requirement unchanged.
2. Probe Japanese VPN Gate candidates one at a time.
3. Limit each candidate to roughly 15–20 seconds.
4. After connection, query radiko's own area detection and record the returned `JPxx` value.
5. Prefer a candidate that gives a stable radiko response, then retry Premium authentication and playback through that network path.
6. If Premium authentication itself is rejected/invalid, stop and report a Premium authentication error. Do not treat VPN as a substitute for Premium.

## Verified region-probe result (2026-08-28 JST)

A 20-candidate test produced 16 successful VPN connections. radiko itself detected exits including:

- JP1 (Hokkaido)
- JP8 (Ibaraki)
- JP13 (Tokyo)
- JP23 (Aichi)
- JP26 (Kyoto)
- JP27 (Osaka)
- JP28 (Hyogo)

One connected candidate returned an unknown area and four candidates failed to connect.

## Files / workflows to retain

- `.github/workflows/radiko_vpngate_regions.yml` — manual region diagnostic. Do not delete when cleaning old test workflows.
- `radiko_proxy.py` — main local proxy.
- `radiko_proxy_start.bat` — Windows launcher.

The region diagnostic is intentionally kept separate from normal operation so a VPN Gate outage cannot break the primary Premium path.
