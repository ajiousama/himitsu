# Local Station EPG Mapping

This step turns the URL-free local station A-candidate registry into practical metadata for M3U/EPG matching.

## Files

- `japan_iptv_local_station_epg_map.csv`
  - one row per local-station A candidate
  - preferred `tvg-id`
  - alternate `tvg-id` candidates
  - display aliases
  - confidence and next action

- `japan_iptv_local_station_aliases.csv`
  - one row per alias
  - maps display-name and slug/name variations back to one `channel_key`

## What this is for

Use these files to normalize names before generating or checking an M3U.

Example flow:

1. Read a candidate channel name or `tvg-id` from an M3U-like source.
2. Look it up in `japan_iptv_local_station_aliases.csv`.
3. Resolve it to `channel_key`.
4. Read the preferred `tvg-id` from `japan_iptv_local_station_epg_map.csv`.
5. Use that preferred ID when comparing against EPG data.

## What this is not

This is not a playback list.

Do not add:

- direct stream URLs
- token/vhash/ac_tk values
- p2p/p5p entries
- private source data

## Next practical step

Create a small local script that checks whether each preferred `tvg-id` exists in the actual EPG XML used by the project.

Recommended next file:

- `scripts/check_local_station_epg_ids.py`

The script should report:

- found preferred IDs
- missing preferred IDs
- matched alternate IDs
- unresolved channels

Keep the script focused on ID matching only. It should not fetch or test playback URLs.
