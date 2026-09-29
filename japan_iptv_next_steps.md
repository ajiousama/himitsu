# Japan IPTV Research Registry - Next Steps

This file explains how to continue the URL-free research registry.

## Goal

Keep this repository as a research index, not a playback list.

The registry is used to decide which candidate groups are worth investigating further by comparing:

- category
- system family
- source family
- freshness
- confidence
- decision rank

No direct stream URLs, token values, vhash values, p2p/p5p entries, or detailed premium channel slug lists should be committed.

## Current stage

The current branch adds a safe root-level registry. It is not meant to generate a playable M3U yet.

Current status:

1. System families are listed.
2. Source families are listed.
3. Decision rules are listed.
4. Search backlog is listed.
5. Group-level candidates are listed.
6. A blank channel template is available for future manual notes.

## Recommended order

### 1. Local/regional stations

Priority: highest

Reason: these are the most useful missing pieces and usually easiest to classify safely.

Track only:

- station name
- region
- source family
- evidence source
- freshness
- decision rank

### 2. General BS and free-adjacent groups

Priority: high

Reason: useful for EPG and channel mapping.

Track only group-level information unless a source is official or clearly free.

### 3. CS genre groups

Priority: medium

Reason: useful for classification, but avoid turning the repository into a playback index.

Track by genre group only:

- cinema
- drama
- anime/kids
- sports/hobby
- documentary
- music
- Asian entertainment

### 4. Sensitive or paid-looking groups

Priority: hold

Reason: keep as category notes only.

Do not commit direct identifiers, direct URLs, vhash values, token values, p2p/p5p data, or detailed playback slugs.

## Decision rank

Use these values:

- A_RESEARCH_TARGET: worth investigating further
- B_WATCH: keep, but not first priority
- C_REFERENCE_ONLY: useful as source context only
- X_EXCLUDE: do not use

## Suggested manual workflow

1. Open `japan_iptv_research_groups.csv`.
2. Pick one row with high priority.
3. Search public GitHub or known public source indexes.
4. Record only source family and evidence summary.
5. Update rank if needed.
6. Do not paste direct playback URLs.

## Output target

The next useful output is not a playable playlist.

The next useful output is:

- `local_station_research.csv`
- `cs_group_research.csv`
- `bs_group_research.csv`

Each should remain URL-free.
