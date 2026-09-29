# Local Station EPG Checker

This is the next practical step after the URL-free local station registry.

## Purpose

Check whether the preferred `tvg-id` values in:

- `japan_iptv_local_station_epg_map.csv`

exist in a local XMLTV EPG file such as:

- `epg.xml`
- generated 3-day EPG XML
- another local guide XML

This does not check playback URLs.

## Usage

```bash
python scripts/check_local_station_epg_ids.py \
  --epg epg.xml \
  --map japan_iptv_local_station_epg_map.csv \
  --out local_station_epg_check_result.csv
```

## Output

The output CSV contains:

- `channel_key`
- `display_name`
- `status`
- `matched_epg_id`
- `preferred_tvg_id`
- `checked_candidates`
- `note`

## Status meanings

- `OK`: at least one preferred or alternate ID exists in the EPG XML.
- `MISSING`: no preferred, alternate, or slug hint matched the EPG XML.

## Next action

When a row is `MISSING`, choose one of these:

1. Add the actual EPG channel ID to `tvg_id_alternates`.
2. Change `tvg_id_preferred` if the preferred ID was wrong.
3. Keep the row as missing if the EPG source does not include that station.

Keep this workflow URL-free. Playback URLs, token values, vhash values, p2p/p5p entries, and private source data do not belong in this repository.
