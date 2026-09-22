# logos system

Canonical shared logo system.

Assets:
- `logos/contrast/` — contrast-normalized TV/radio logos
- `logos/ehime_catv/` — Ehime CATV logos
- `logos/public_sports/venues/` — KEIRIN / AutoRace / local-racing venue logos
- `logos/tools/` — shared logo generators and normalizers
- `logos/contrast_sources.json` — source mapping for generated contrast logos

Ownership:
- shared/common logos live here
- YouTube-specific generated logos stay under `youtube/logos/` because they are tied to the YouTube subsystem
- FreeWiFi only references the generated assets; it does not own them

Root-level legacy logo scripts may remain temporarily as compatibility shims, but new changes should target `logos/tools/`.
