# Newblog backups are kept only in yovi (since 2026-10-28)

- The 101 approved newblog source entries and their rolling approved 14-day replay shelf belong to yovi only.
- Run `python newblog/sync_yovi.py`; it also removes legacy newblog entries from FreeWiFi and the canonical `tv/playlist.m3u`.
- The retired importer `newblog/sync_tv.py` is deliberately blocked from restoring FreeWiFi sources.
- Rakuten/Rch refresh no longer reinserts newblog Nouvelle Paradise or Pigoo.
- The 17 approved YoiTV CS, all original 5002 URLs, and 66 Shinori sources remain unchanged in FreeWiFi.
- All background workflows must call `newblog/sync_yovi.py`, never the old FreeWiFi importer.
- `scripts/check_tv_source_partition.py` blocks any future newblog re-entry into FreeWiFi or TV canonical.
- The master source refresh still updates `newblog/source.m3u` only after validation and then the canonical sync reads it.
- Do not expose upstream credentials in logs, metadata, or README files.
