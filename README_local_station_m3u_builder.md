# Local Station M3U Builder

This is the practical step after the local-station research registry.

It converts a private local CSV into an M3U file.

## Files

- `japan_iptv_local_station_m3u_private_template.csv`
- `scripts/build_local_station_m3u_from_private_csv.py`

## Important rule

Do not commit filled playback URLs to this repository.

The template keeps `stream_url` blank on purpose.

Use it like this:

1. Copy the template locally.
2. Fill `stream_url` on your own device only.
3. Optionally change `input_status` from `未入力` to `入力済み` for your own tracking.
4. Run the builder script.
5. Use the generated M3U privately.

## Template columns

The template is designed so only one column needs private input:

- `fill_order`: recommended order for checking candidates.
- `channel_key`: stable local station key.
- `display_name`: display name used in the generated M3U.
- `alias_hint`: common naming variations to help identify the channel.
- `group_title`: M3U group title.
- `tvg_id`: M3U `tvg-id` value.
- `tvg_name`: M3U `tvg-name` value.
- `priority`: research priority.
- `system_family`: candidate system family, stored as metadata only.
- `input_status`: local tracking field, such as `未入力` or `入力済み`.
- `input_note`: local reminder notes.
- `stream_url`: blank by design; fill locally only.

## Example

```bash
cp japan_iptv_local_station_m3u_private_template.csv local_station_private.csv
```

Edit `local_station_private.csv` locally and fill only the `stream_url` column.

Then run:

```bash
python scripts/build_local_station_m3u_from_private_csv.py \
  --csv local_station_private.csv \
  --out local_station_private.m3u \
  --include-missing
```

## Output

The script writes:

```text
local_station_private.m3u
```

Rows with blank `stream_url` are skipped.

## What this does not do

This script does not:

- search for playback URLs
- scrape websites
- bypass authentication
- validate paid or restricted streams
- store token/vhash/ac_tk values
- commit private URLs

It only formats metadata plus user-supplied private URLs into an M3U file.

## Next step

After building the M3U locally, compare the `tvg-id` values against the EPG map:

- `japan_iptv_local_station_epg_map.csv`
- `japan_iptv_local_station_aliases.csv`

Use `scripts/check_local_station_epg_ids.py` later only when you want to verify that the IDs exist inside a real `epg.xml`.
