# Japan IPTV Local Station Research

This file tracks the next safe research step after the URL-free IPTV registry.

## Purpose

Keep regional and local station candidates separate from BS/CS candidates.

This registry is intentionally URL-free. It stores only:

- station name
- region
- candidate system family
- slug or ID hint
- EPG ID hint
- priority
- decision status
- next action

It must not store direct playback URLs, token values, vhash values, p2p/p5p entries, or private source data.

## Priority order

1. Local independent stations
   - チバテレ
   - tvk
   - テレ玉
   - TOKYO MX2
   - KBS京都
   - サンテレビ

2. Kansai wide-area stations
   - MBS
   - ABC
   - YTV
   - 関西テレビ
   - テレビ大阪

3. Secondary/local fragments
   - テレビ新広島
   - テレビ東京 fragments
   - NHK regional variants

## Decision rule

- `A_本命候補`: multiple public GitHub appearances or clear system/slug match.
- `B_保留候補`: promising but needs more corroboration.
- `C_資料`: useful as a reference only.
- `X_除外`: old, p2p, token-heavy, or unsuitable.

## Next work

Create a follow-up group file only after the local station registry is stable:

- `japan_iptv_bs_research.csv`
- `japan_iptv_cs_movie_research.csv`
- `japan_iptv_anime_kids_research.csv`
- `japan_iptv_sports_hobby_research.csv`

Keep every file URL-free.
