# FreeWiFi edge migration

This directory stages lightweight FreeWiFi APIs for Cloudflare Workers so Render can be reserved for heavy/browser/ffmpeg workloads.

Endpoints:
- `/health` — status
- `/proxy?url=...` — allowlisted HLS/media proxy with playlist rewriting
- `/kick?ch=...` — KICK live resolver
- `/kick?vod=...&start=...&duration=...` — KICK VOD seek/clip playlist
- `/haru-clip?src=...&offset=...&duration=...` — HARU replay clip playlist

This is intentionally staged on `infra-split-render-20260927` first. Do not switch production M3U URLs until the Worker is deployed and endpoint tests pass.

Render should remain only for workloads that require a persistent process, Chromium/Playwright/Puppeteer, or ffmpeg.
