import unittest
import numpy as np

from gmcx_logo_search import (
    FRAME_SIZE, HEIGHT, WIDTH, logo_metrics, looks_like_logo, scan_bytes, vetoed
)


def black_with_gold(central=True):
    img = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    if central:
        img[23:29, 15:75] = (190, 165, 42)
    else:
        img[1:7, 1:9] = (190, 165, 42)
    return img.tobytes()


class LogoSearchTests(unittest.TestCase):
    def test_potential_title_logo_needs_black_and_central_gold(self):
        metrics = logo_metrics(black_with_gold())
        self.assertTrue(looks_like_logo(metrics))
        self.assertGreater(metrics["gold"], 0.018)

    def test_small_corner_overlay_not_title_logo(self):
        self.assertFalse(looks_like_logo(logo_metrics(black_with_gold(False))))

    def test_full_bright_frame_is_not_title_logo(self):
        img = np.full((HEIGHT, WIDTH, 3), (145, 180, 195), dtype=np.uint8)
        self.assertFalse(looks_like_logo(logo_metrics(img.tobytes())))

    def test_rejects_incomplete_frames(self):
        with self.assertRaises(ValueError):
            logo_metrics(b"\x00" * (FRAME_SIZE - 1))

    def test_contiguous_hits_collapse_without_claiming_episode(self):
        black = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8).tobytes()
        found = scan_bytes(black + black_with_gold() * 2 + black, 1000)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["first_seconds"], 1002)
        self.assertEqual(found[0]["last_seconds"], 1004)
        self.assertNotIn("episode", found[0])

    def test_video_veto_applies_only_to_original_recording(self):
        known = [{"vod_prefix": "df1386fd", "seconds": 59096.0}]
        self.assertTrue(vetoed("df1386fd-123", 59100.0, known))
        self.assertFalse(vetoed("5847ae05-123", 59100.0, known))


if __name__ == "__main__":
    unittest.main()
