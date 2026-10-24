"""Regression tests for newblog URL refresh: no destructive updates."""
import unittest
from unittest.mock import call, patch
from refresh_source import UnsafeSource, update_source, download_source, PUBLIC_MIRROR


def row(slug: str, token: str = "old", name: str = "Station") -> str:
    return (f'#EXTINF:-1 group-title="JP",{name}\n'
            f'https://0i4neux01.charandom.blog/stream/jp/{slug}/stream-output.m3u8?ac_tk={token}&mode=hls\n')


class TestNewblogRefresh(unittest.TestCase):
    def setUp(self):
        self.old = '#EXTM3U url-tvg="original"\n\n' + row("nhk_g") + "\n" + row("tbs")
        self.approved = {"nhk_g", "tbs"}

    def test_update_url_and_keep_order(self):
        master = "#EXTM3U\n\n" + row("tbs", "new") + "\n" + row("nhk_g", "new")
        updated, changed, unknown = update_source(self.old, master, self.approved)
        self.assertEqual(set(changed), self.approved)
        self.assertEqual(unknown, [])
        self.assertTrue(updated.startswith('#EXTM3U url-tvg="original"'))
        self.assertLess(updated.index("/nhk_g/"), updated.index("/tbs/"))
        self.assertNotIn("ac_tk=old", updated)

    def test_new_station_is_reported_not_added(self):
        master = "#EXTM3U\n" + row("nhk_g") + row("tbs") + row("extra")
        updated, changed, unknown = update_source(self.old, master, self.approved)
        self.assertEqual(changed, [])
        self.assertEqual(unknown, ["extra"])
        self.assertNotIn("/extra/", updated)

    def test_missing_station_blocks_publish(self):
        with self.assertRaisesRegex(UnsafeSource, "Missing 1 approved"):
            update_source(self.old, "#EXTM3U\n" + row("nhk_g", "new"), self.approved)

    def test_error_page_blocks_publish(self):
        with self.assertRaises(UnsafeSource):
            update_source(self.old, "<html>please log in</html>", self.approved)

    def test_missing_token_blocks_publish(self):
        master = "#EXTM3U\n" + row("nhk_g", "new") + row("tbs", "new").replace("ac_tk=new&", "other=1&")
        with self.assertRaisesRegex(UnsafeSource, "no access token"):
            update_source(self.old, master, self.approved)

    def test_duplicate_station_blocks_publish(self):
        master = "#EXTM3U\n" + row("nhk_g") + row("nhk_g") + row("tbs")
        with self.assertRaisesRegex(UnsafeSource, "Duplicate"):
            update_source(self.old, master, self.approved)

    def test_public_mirror_only_on_authentication_error(self):
        secret = "https://0i4neux01.charandom.blog/stream/master.m3u?pass=not-a-real-password"
        text = "#EXTM3U\n"
        with patch("refresh_source._fetch_playlist", side_effect=[
            UnsafeSource("Failed to retrieve master M3U (HTTP 401)"), text
        ]) as loader:
            self.assertEqual(download_source(secret), text)
            self.assertEqual(loader.call_args_list, [
                call(secret, label="master"),
                call(PUBLIC_MIRROR, label="public mirror"),
            ])

    def test_public_mirror_not_used_for_other_errors(self):
        secret = "https://0i4neux01.charandom.blog/stream/master.m3u?pass=not-a-real-password"
        with patch("refresh_source._fetch_playlist", side_effect=UnsafeSource("Bad redirect")) as loader:
            with self.assertRaisesRegex(UnsafeSource, "Bad redirect"):
                download_source(secret)
            loader.assert_called_once_with(secret, label="master")

    def test_unapproved_metadata_change_blocks_publish(self):
        master = "#EXTM3U\n" + row("nhk_g", "new").replace(
            'group-title="JP"', 'group-title="UNTRUSTED"'
        ) + row("tbs", "new")
        with self.assertRaisesRegex(UnsafeSource, "Unapproved metadata change"):
            update_source(self.old, master, self.approved)

    def test_unapproved_stream_options_block_publish(self):
        master = "#EXTM3U\n" + row("nhk_g", "new") + row("tbs", "new").replace(
            "&mode=hls", "&mode=other"
        )
        with self.assertRaisesRegex(UnsafeSource, "Unapproved stream URL change"):
            update_source(self.old, master, self.approved)

    def test_unrelated_region_ignored(self):
        master = "#EXTM3U\n" + row("nhk_g") + row("tbs") + '#EXTINF:-1,International\nhttps://example.com/stream/foreign.m3u8\n'
        _, _, unknown = update_source(self.old, master, self.approved)
        self.assertEqual(unknown, [])


if __name__ == "__main__":
    unittest.main()
