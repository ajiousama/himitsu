# FreeWiFi newblog master-M3U refresh

The approved station registry is **newblog/channel_map.json** (101 channels).
The FreeWiFi importer is **newblog/sync_tv.py**, already called by
.github/workflows/update_freewifi_epg.yml (scheduled hourly at minute 07).

newblog/refresh_source.py adds a fetch step without changing the 101 approved
stations, station order, EPG tvg-ids, or logos. It edits newblog/source.m3u only
when source metadata/URLs change. The existing FreeWiFi workflow then rebuilds
tv/playlist.m3u and freewifi because it watches changes to newblog/**.

## One-time setup

GitHub repository → Settings → Secrets and variables → Actions → New repository secret:

- Name: NEWBLOG_MASTER_URL
- Value: the full authorized HTTPS newblog /stream/master.m3u URL, including
  mode=hls and the pass parameter.

Never commit this master URL/password to YAML, source code, docs, or issues.
Run Actions → Refresh newblog source M3U → Run workflow to verify setup.

The refresh schedule runs hourly at minute 41 (UTC; minute 41 in Japan too).
GitHub scheduled workflow start times may be delayed.

## Safety behavior

- Update only the existing 101 approved station slugs.
- Ignore stations from unrelated regions.
- Report new JP station slugs in Actions logs and job summary without adding them.
- Reject missing approved stations, HTML error pages, duplicate JP stations,
  malformed links and missing per-stream ac_tk.
- On a failure do not overwrite the last good source.m3u.
- Keep HARUKA/NAORI removed through the existing FreeWiFi cleanup scripts.
- Verify playback separately: structural validation cannot guarantee playback.

The source.m3u and FreeWiFi playlist already contain upstream stream URLs with
access tokens. Confirm upstream permission to republish streams or tokens.
