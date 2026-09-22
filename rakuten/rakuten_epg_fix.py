from __future__ import annotations

import xml.etree.ElementTree as ET

from rakuten.rakuten_epg_backup import (
    GUIDES,
    RAKUTEN_CHANNELS,
    current_real_programmes,
    fetch_official,
    previous_guides_root,
    replace_with_official,
    replace_with_previous,
    update_report,
)

# Keep the authoritative Rakuten pass aligned with every Rch entry currently
# published in freewifi. Mutating the imported mapping also updates the mapping
# used internally by rakuten_epg_backup.fetch_official()/parse_official_html().
RAKUTEN_CHANNELS.update({
    "rch_35": "パチンコ・パチスロ",
    "rch_37": "エンタメ～テレDEEP",
    "rch_86": "ワンニャンチャンネル",
    "rch_113": "ぷれいば！ ～ゲーム専門チャンネル～",
    "rch_46": "釣り",
})


def main() -> int:
    if not GUIDES.exists():
        print("RAKUTEN FIX: guides.xml missing; skipped")
        return 0

    root = ET.parse(GUIDES).getroot()
    official, errors = fetch_official()
    previous = previous_guides_root()
    applied: dict[str, tuple[str, int]] = {}

    # Rakuten channels are deliberately handled after the generic EPG merge.
    # A generic source may have a syntactically valid rch_* schedule that is
    # stale or belongs to a similarly named channel, so validity alone is not
    # enough. When Rakuten's official schedule is available, it is authoritative
    # and always replaces the generic EPG for that channel.
    for cid in RAKUTEN_CHANNELS:
        rows = official.get(cid) or []
        if rows:
            count = replace_with_official(root, cid, rows)
            applied[cid] = ("rakuten-official", count)
            continue

        # If the official page could not be parsed, keep a current real grid.
        # Only fall back to the previous known-good guide when the channel would
        # otherwise have no current real programme data at all.
        if current_real_programmes(root, cid):
            continue
        if previous is not None:
            count = replace_with_previous(root, previous, cid)
            if count:
                applied[cid] = ("previous-good-cache", count)

    ET.ElementTree(root).write(GUIDES, encoding="utf-8", xml_declaration=True)
    update_report(applied, errors)

    remaining = [cid for cid in RAKUTEN_CHANNELS if not current_real_programmes(root, cid)]
    print(f"RAKUTEN FIX: applied={applied} remaining={remaining}")
    if errors:
        print("RAKUTEN FIX: official diagnostics:")
        for line in errors[-5:]:
            print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
