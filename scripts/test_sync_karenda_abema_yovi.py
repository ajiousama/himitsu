"""Regression tests for the yovi karenda ABEMA系 synchronizer."""
import unittest

from sync_karenda_abema_yovi import (
    BEGIN,
    END,
    GROUP,
    parse_source,
    update_yovi,
)


def sample_source(ids=("abema-news", "motor-sport")):
    entries = ["#EXTM3U url-tvg=\"guide\""]
    for name in ids:
        entries += [
            (
                f'#EXTINF:-1 tvg-id="{name}" '
                f'tvg-logo="https://image.p-c2-x.abema-tv.com/image/channels/'
                f'{name}/logo.png?height=48" group-title="Abema_240p" ,{name}'
            ),
            f"https://linear-abematv.akamaized.net/preview/channel/{name}/playlist.m3u8",
            "",
        ]
    return "\n".join(entries)


class KarendaAbemaSyncTest(unittest.TestCase):
    def test_group_and_count(self):
        entries = parse_source(sample_source(), min_channels=2)
        self.assertEqual(len(entries), 2)
        for ext, url in entries:
            self.assertIn('group-title="ABEMA系"', ext)
            self.assertIn("linear-abematv.akamaized.net", url)
        self.assertIn("motor-sport", entries[1][1])

    def test_preserves_unrelated_entries_and_groups_existing_promo(self):
        playlist = (
            "#EXTM3U url-tvg=\"leave alone\"\n"
            '#EXTINF:-1 group-title="PrimeHome",🟢PrimeHome\n'
            'https://example.net/keep-ph.m3u8\n'
            '#EXTINF:-1 tvg-id="commercial" group-title="RavenTV-JP", AbemaTV Promo (VPN)\n'
            'https://ds-linear-abematv.akamaized.net/channel/commercial/manifest.mpd\n'
            '#EXTINF:-1 group-title="CS YoiTV",🟢Keep YoiTV\n'
            'https://example.net/keep-yoitv.m3u8\n'
        )
        entries = parse_source(sample_source(), min_channels=2)
        updated = update_yovi(playlist, entries)
        self.assertIn('group-title="ABEMA系", AbemaTV Promo (VPN)', updated)
        self.assertIn('group-title="PrimeHome",🟢PrimeHome', updated)
        self.assertIn('group-title="CS YoiTV",🟢Keep YoiTV', updated)
        self.assertIn('https://example.net/keep-ph.m3u8', updated)
        self.assertIn('https://example.net/keep-yoitv.m3u8', updated)
        self.assertEqual(updated.count(BEGIN), 1)
        self.assertEqual(updated.count(END), 1)
        self.assertEqual(update_yovi(updated, entries), updated)

    def test_future_changes_replace_only_managed_block(self):
        start = "#EXTM3U\n# keep\n"
        first = parse_source(sample_source(), min_channels=2)
        next_entries = parse_source(sample_source(("motor-sport", "new-channel")), min_channels=2)
        existing = update_yovi(start, first)
        changed = update_yovi(existing, next_entries)
        self.assertTrue(changed.startswith(start))
        self.assertIn("new-channel", changed)
        self.assertNotIn("abema-news", changed)
        self.assertEqual(changed.count(BEGIN), 1)

    def test_rejects_bad_source_and_duplicate(self):
        with self.assertRaises(ValueError):
            parse_source("not a playlist", min_channels=2)
        with self.assertRaises(ValueError):
            parse_source(sample_source(("abema-news", "abema-news")), min_channels=2)
        broken = sample_source().replace("linear-abematv.akamaized.net", "example.invalid")
        with self.assertRaises(ValueError):
            parse_source(broken, min_channels=2)

    def test_rejects_broken_existing_markers(self):
        entries = parse_source(sample_source(), min_channels=2)
        with self.assertRaises(ValueError):
            update_yovi("#EXTM3U\n" + BEGIN + "\n", entries)


if __name__ == "__main__":
    unittest.main()
