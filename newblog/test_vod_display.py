"""Regression checks for user-facing newblog/GCCX replay labels."""
import unittest
from sync_tv import format_vod_display


class TestGccxVodDisplay(unittest.TestCase):
    def entry(self, detail, episode_id="gccx_one"):
        return {
            "id": episode_id,
            "start": 1792357200,  # 2026-10-19 06:00 JST
            "title": "📼 ゲームセンターCX（フジテレビONE放送分） 10/19 06:00｜" + detail,
            "tvg_name": "ゲームセンターCX（フジテレビONE放送分）",
        }

    def test_regular_episode_starts_with_challenged_game(self):
        title, name = format_vod_display(
            self.entry('ゲームセンターCX　#424　出撃せよ！「スターフォックス64」'))
        self.assertEqual(
            title,
            "📼 スターフォックス64 #424｜ゲームセンターCX 10/19 06:00｜出撃せよ！",
        )
        self.assertEqual(name, "スターフォックス64 #424｜ゲームセンターCX")

    def test_archive_episode_starts_with_game(self):
        title, name = format_vod_display(
            self.entry('ゲームセンターCX 有野の挑戦 アーカイブス　#179「夢ペンギン物語」に挑戦'))
        self.assertEqual(
            title, "📼 夢ペンギン物語 #179｜ゲームセンターCX アーカイブス 10/19 06:00")
        self.assertEqual(name, "夢ペンギン物語 #179｜ゲームセンターCX アーカイブス")

    def test_special_without_game_leads_with_specific_subject(self):
        title, name = format_vod_display(
            self.entry("ゲームセンターCX たまに行くなら九州弾丸ツアー"))
        self.assertEqual(title, "📼 たまに行くなら九州弾丸ツアー｜ゲームセンターCX 10/19 06:00")
        self.assertTrue(name.startswith("たまに行くなら九州弾丸ツアー"))

    def test_other_vod_is_completely_unchanged(self):
        item = self.entry("探偵！ナイトスクープ", "knight_scoop")
        self.assertEqual(format_vod_display(item), (item["title"], item["tvg_name"]))

    def test_unrecognised_gccx_title_preserved(self):
        item = self.entry("")
        item["title"] = "📼 ゲームセンターCX"
        self.assertEqual(format_vod_display(item), (item["title"], item["tvg_name"]))


if __name__ == "__main__":
    unittest.main()
