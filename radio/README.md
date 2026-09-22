# radio system

Canonical radio system for FreeWiFi and standalone radio playback.

Outputs:
- `freewifi.m3u` — compact 19-station FreeWiFi selection
- `nationwide.m3u` — nationwide Radiko catalog, excluding duplicate NHK entries
- `nhk.m3u` — NHK Radio 1 / NHK-FM regional feeds
- `playlist.m3u` — combined nationwide + NHK standalone catalog

Playback policy:
- all three user-facing radio playlists use the same **static-image + audio video playback** route
- URLs point to `https://ajiousama-radiko.onrender.com/radio-tv/<station>`
- the Render muxer generates a station card/logo still image and combines it with live radio audio
- raw audio-only HLS and the old `radio-ts-assets` route are not the canonical playback method

NHK:
- `update_nhk.py` refreshes official NHK R1/FM source URLs
- `nhk_stations.json` feeds those audio sources to the Render static-image muxer
- `build_playlist.py` combines `nationwide.m3u` + `nhk.m3u`

Compatibility:
- root `radio.m3u` remains a mirror of `radio/playlist.m3u`
- root `freewifi` keeps only the compact 19-station radio block
