"""Offline regression: identify full GCCX game titles, not publisher fragments."""
import unittest

from gmcx_unknown_title_probe import identify_title


class GCCXOCRTitles(unittest.TestCase):
    def test_taito_copyright_does_not_become_chase_hq(self):
        titles = {"211": "TAITO CHASE H.Q."}
        self.assertIsNone(identify_title("©TAITO CORP./ ビートたけし 1986", titles))

    def test_generic_core_does_not_become_armored_core(self):
        titles = {"387": "ARMORED CORE"}
        self.assertIsNone(identify_title("core 2009 / Score Color game", titles))

    def test_full_visible_game_title(self):
        titles = {"211": "TAITO CHASE H.Q."}
        match = identify_title("TAITO CHASE H.Q.", titles)
        self.assertIsNotNone(match)
        self.assertEqual(match["episode"], 211)

    def test_sequel_number_must_not_match_base_game(self):
        titles = {"46": "ロックマン"}
        self.assertIsNone(identify_title("ロックマン2に挑戦", titles))

    def test_base_game_still_matches(self):
        titles = {"46": "ロックマン"}
        self.assertEqual(identify_title("ロックマン", titles)["episode"], 46)

    def test_ambiguous_shared_title_requires_more_evidence(self):
        titles = {"92": "風来のシレン（前編）", "93": "風来のシレン（後編）"}
        self.assertIsNone(identify_title("風来のシレン", titles))


if __name__ == "__main__":
    unittest.main()
