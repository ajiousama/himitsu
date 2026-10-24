"""Regression tests for newblog URL refresh: no destructive updates."""
import unittest
from unittest.mock import call, patch
from refresh_source import (UnsafeSource, update_source, download_source, PUBLIC_MIRROR,
                            extract_kamonka_tokens, apply_kamonka_tokens, choose_source, KAMONKA_MIRROR)


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


    def test_kamonka_plaintext_imports_only_whitelisted_slugs(self):
        approved = {f"station_{i:03d}" for i in range(90)}
        plaintext = "\n".join(
            f"Japanese {slug},https://0i4nEUX01.charandom.blog/stream/jp/{slug}/stream-output.m3u8?ac_tk=example.long.token-1234567890123456789&mode=hls"
            for slug in sorted(approved)
        )
        plaintext += "\nUnrelated,https://untrusted.example/stream/jp/other/stream-output.m3u8?ac_tk=arbitrary&mode=hls"
        result = extract_kamonka_tokens(plaintext, approved)
        self.assertEqual(set(result), approved)
        self.assertEqual(len(set(result.values())), 1)

    def test_kamonka_infers_shared_token_for_missing_channels_and_catchup(self):
        old = ('#EXTM3U\n' +
               '#EXTINF:-1 catchup-source="https://0i4neux01.charandom.blog/stream/jp/nhk_g/replay.m3u8?ac_tk=old&mode=hls&start=123",NHK\n'
               'https://0i4neux01.charandom.blog/stream/jp/nhk_g/stream-output.m3u8?ac_tk=old&mode=hls\n' +
               row("tbs"))
        updated, changed = apply_kamonka_tokens(old, {"nhk_g": "valid-kamonka"}, self.approved)
        self.assertEqual(set(changed), self.approved)
        self.assertIn("ac_tk=valid-kamonka&mode=hls", updated)
        self.assertNotIn("ac_tk=old&mode=hls", updated)
        self.assertEqual(updated.count("ac_tk=valid-kamonka"), 3)
        self.assertIn("start=123", updated)
        self.assertIn("/stream/jp/tbs/stream-output.m3u8?ac_tk=valid-kamonka&mode=hls", updated)

    def test_kamonka_rejects_inconsistent_tokens(self):
        approved = {f"station_{i:03d}" for i in range(90)}
        plaintext = "\n".join(
            f"{slug},https://0i4neux01.charandom.blog/stream/jp/{slug}/stream-output.m3u8?ac_tk=abcdefghijklmnop1234567890.{i%2}0123456789&mode=hls"
            for i, slug in enumerate(sorted(approved))
        )
        with self.assertRaisesRegex(UnsafeSource, "inconsistent"):
            extract_kamonka_tokens(plaintext, approved)

    def test_unverified_candidates_preserve_existing_playlist(self):
        zx = "#EXTM3U\n" + row("nhk_g", "zx") + row("tbs", "zx")
        with patch("refresh_source._fetch_playlist", side_effect=[zx, "kamonka text"]), \
             patch("refresh_source.extract_kamonka_tokens", return_value={"nhk_g":"k"}), \
             patch("refresh_source.probe_candidate", return_value="unknown"):
            updated, selected, changed = choose_source(self.old, "", self.approved)
        self.assertEqual(updated, self.old)
        self.assertEqual(selected, "preserved")
        self.assertEqual(changed, 0)

    def test_verified_kamonka_overrides_expired_zx(self):
        zx = "#EXTM3U\n" + row("nhk_g", "expired") + row("tbs", "expired")
        with patch("refresh_source._fetch_playlist", side_effect=[zx, "kamonka text"]), \
             patch("refresh_source.extract_kamonka_tokens", return_value={"nhk_g":"valid", "tbs":"valid"}), \
             patch("refresh_source.probe_candidate", side_effect=lambda body, name: "ok" if name == "kamonka" else "forbidden"):
            updated, selected, changed = choose_source(self.old, "", self.approved)
        self.assertEqual(selected, "kamonka")
        self.assertEqual(changed, 2)
        self.assertIn("ac_tk=valid", updated)
        self.assertNotIn("ac_tk=expired", updated)



if __name__ == "__main__":
    unittest.main()
