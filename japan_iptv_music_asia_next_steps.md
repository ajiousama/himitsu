# Japan IPTV Music / Asia Research Next Steps

This file tracks the next work for the URL-free music and Asia/Korean entertainment research registry.

## Scope

Target category groups:

- Music CS core
- Japanese music / pop channels
- International music channels
- Korean and Asia entertainment channels
- Official/free reference candidates where applicable

## Rules

- Keep the registry URL-free.
- Do not add direct stream URLs.
- Do not add token, vhash, ac_tk, cookie, or authorization values.
- Do not add p2p or p5p entries.
- Keep premium or subscription-channel details at group level only.
- Use source freshness, repeated appearance, and system family as research signals.

## Suggested workflow

1. Review group rows in `japan_iptv_music_asia_research.csv`.
2. For each group, collect only source-level notes: source family, source path/name, freshness, and category.
3. Keep any detailed playback identifiers in local-only notes, not in the public repository.
4. Promote only safe, URL-free findings into the registry.

## Priority

1. KBS World / official-or-free reference context
2. Mnet / KNTV / Asia entertainment group
3. Music Japan TV / MUSIC ON! TV / MTV group
4. Space Shower / Music Air / Japanese music group

## Output style

Future additions should use group-level rows such as:

```csv
category,group_name,example_channels,known_system_families,research_priority,decision_policy,notes
```

