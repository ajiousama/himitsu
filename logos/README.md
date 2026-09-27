# logos system

Canonical shared logo system.

Assets:
- `logos/contrast/` — contrast-normalized TV/radio logos
- `logos/ehime_catv/` — Ehime CATV logos
- `logos/public_sports/venues/` — fixed production venue logos
- `logos/tools/` — active normalizers and validators only
- `logos/contrast_sources.json` — source mapping for generated contrast logos
- `logos/fixed_logo_manifest.json` — immutable BOAT RACE / AutoRace production logo hashes

Pinned sports-logo policy:
- BOAT RACE 24 venue PNGs and AutoRace 5 venue PNGs are fixed assets.
- Do not regenerate, redraw, or replace them from a generator during routine maintenance.
- `python logos/tools/validate_fixed_sports_logos.py` must pass before FreeWiFi publishing.
- BOAT RACE uses the approved set with `からつ` / `まるがめ` in hiragana and night identification on the seven approved night venues.
- AutoRace uses the approved five-venue design without event-type badges.

Ownership:
- shared/common logos live here
- YouTube-specific generated logos stay under `youtube/logos/` because they are tied to the YouTube subsystem
- FreeWiFi references these assets; it must not regenerate pinned sports logos
