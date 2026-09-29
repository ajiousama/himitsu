# Optional local-station M3U import

This repository does not store private local-station stream URLs.

Use `ajiousama/japan-iptv-research` to create a local-only file named:

```text
local_station_private.m3u
```

Place that file in the root of this working copy when you want to add those channels to the local output.

## Merge locally

```powershell
powershell -ExecutionPolicy Bypass -File scripts/merge_optional_local_station_m3u.ps1
```

Default behavior:

```text
Base input:   freewifi
Private add:  local_station_private.m3u
Output:       freewifi_with_local_station.m3u
```

If `local_station_private.m3u` is missing, the script writes a base-only output and does not fail.

## Custom paths

```powershell
powershell -ExecutionPolicy Bypass -File scripts/merge_optional_local_station_m3u.ps1 `
  -BaseM3U freewifi `
  -LocalStationM3U local_station_private.m3u `
  -OutM3U freewifi_with_local_station.m3u
```

## Safety

- No stream URLs are committed here.
- `local_station_private.csv` and `local_station_private.m3u` are ignored by git.
- The script only merges local files already present on the user's PC.
