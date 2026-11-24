from pathlib import Path
import json
import unittest

from youtube import manager


class YouTubeV2StructureTests(unittest.TestCase):
    def test_config_is_single_source_of_truth(self):
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(cfg.get("version"), 2)
        general = cfg.get("general") or []
        self.assertGreaterEqual(len(general), 71)
        ids = [x["id"] for x in general]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("youtube.kana_tube", set(ids))
        self.assertNotIn("youtube.ehime_mandarin", set(ids))

    def test_logos_or_default_are_valid(self):
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        items = list(cfg["general"]) + list(cfg["special"].values())
        for item in items:
            url = item.get("logo")
            if not url:
                self.assertEqual(
                    manager.logo_url(None).split("?", 1)[0],
                    manager.DEFAULT_YOUTUBE_LOGO,
                )
                continue
            self.assertIn("/youtube/logos/", url)
            rel = url.replace("https://raw.githubusercontent.com/ajiousama/himitsu/main/", "")
            self.assertTrue(Path(rel).is_file(), rel)


    def test_kana_prefers_muxed_media_hls_over_adaptive_master(self):
        video = {
            "manifest_url": "https://manifest.googlevideo.com/hls_variant/master.m3u8",
            "formats": [
                {"url": "https://x.googlevideo.com/only-video.m3u8",
                 "protocol": "m3u8_native", "vcodec": "avc1.42001e", "acodec": "none", "height": 1080},
                {"url": "https://x.googlevideo.com/muxed-360.m3u8",
                 "protocol": "m3u8_native", "vcodec": "avc1.42001e", "acodec": "mp4a.40.2", "height": 360},
                {"url": "https://x.googlevideo.com/muxed-720.m3u8",
                 "protocol": "m3u8_native", "vcodec": "avc1.64001f", "acodec": "mp4a.40.2", "height": 720},
            ],
        }
        self.assertEqual(manager.info_hls(video), "https://x.googlevideo.com/muxed-720.m3u8")
        video["formats"] = video["formats"][:1]
        self.assertEqual(manager.info_hls(video), video["manifest_url"])

    def test_kana_freewifi_keeps_separate_youtube_and_iptv_slots(self):
        import re
        text = Path("freewifi").read_text(encoding="utf-8-sig", errors="replace")
        start = text.index(manager.KANA_START)
        end = text.index(manager.KANA_END, start)
        block = text[start:end]
        self.assertEqual(block.count('tvg-id="youtube.kana_tube"'), 1)
        self.assertEqual(block.count('tvg-id="youtube.kana_tube_iptv"'), 1)
        lines = block.splitlines()
        youtube_i = next(i for i, line in enumerate(lines)
                         if 'tvg-id="youtube.kana_tube"' in line)
        iptv_i = next(i for i, line in enumerate(lines)
                      if 'tvg-id="youtube.kana_tube_iptv"' in line)
        self.assertRegex(lines[youtube_i + 1], r"^https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}$")
        self.assertEqual(lines[iptv_i + 1], manager.KANA_9X_PROXY)
        self.assertLess(youtube_i, iptv_i)

    def test_kana_empty_output_keeps_both_freewifi_slots(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            empty_output = Path(tmp) / "kana.m3u"
            empty_output.write_text("#EXTM3U\n", encoding="utf-8")
            previous = Path(tmp) / "freewifi"
            previous.write_text(
                '#EXTM3U\n#EXTINF:-1 tvg-id="youtube.kana_tube",かなチューブ【YouTube】\n'
                'https://www.youtube.com/watch?v=dD3INnBLoVQ\n',
                encoding="utf-8",
            )
            with patch.object(manager, "KANA_OUT", empty_output), patch.object(manager, "FREEWIFI", previous):
                body = manager.kana_managed_body()

        self.assertEqual(body.count('tvg-id="youtube.kana_tube"'), 1)
        self.assertEqual(body.count('tvg-id="youtube.kana_tube_iptv"'), 1)
        self.assertIn("https://www.youtube.com/watch?v=dD3INnBLoVQ", body)
        self.assertIn(manager.KANA_9X_PROXY, body)
        self.assertIn("配信確認中", body)

    def test_kana_has_one_canonical_publication_owner(self):
        removed = (
            ".github/workflows/kana_iptv_v2.yml",
            ".github/workflows/kana_iptv_hls.yml",
            ".github/workflows/kana_iptv_fresh.yml",
            ".github/workflows/kana_iptv_rescue.yml",
            ".github/workflows/kana_iptv_fresh_publish.yml",
            "youtube/kana_iptv_resolver.py",
            "youtube/kana_iptv_v2.py",
        )
        self.assertFalse([path for path in removed if Path(path).exists()])
        diagnostic = Path(".github/workflows/kana_iptv_altapi.yml").read_text(encoding="utf-8")
        self.assertNotIn('gh_put("youtube/output/kana.m3u"', diagnostic)
        self.assertNotIn('gh_put("youtube/output/kana_iptv.m3u"', diagnostic)
        manager_workflow = Path(".github/workflows/update_youtube.yml").read_text(encoding="utf-8")
        self.assertIn("python youtube/manager.py --scope special", manager_workflow)

    def test_kana_validation_accepts_stale_state_and_stable_relay(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            stale_state = Path(tmp) / "kana.json"
            stale_state.write_text(json.dumps({
                "state": "is_live",
                "watch_url": "https://www.youtube.com/watch?v=4WBD_opNgKk",
                "play_url": None,
            }), encoding="utf-8")
            with patch.object(manager, "KANA_STATE", stale_state):
                manager.validate(manager.load_config())

    def test_kana_offline_sync_keeps_both_entries_and_passes_validation(self):
        from tempfile import TemporaryDirectory
        from unittest.mock import patch

        with TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            freewifi = tmp_root / "freewifi"
            freewifi.write_text(Path("freewifi").read_text(encoding="utf-8"), encoding="utf-8")
            kana_output = tmp_root / "kana.m3u"
            kana_output.write_text("#EXTM3U\n", encoding="utf-8")
            offline_state = tmp_root / "kana.json"
            offline_state.write_text(json.dumps({"state": "offline"}), encoding="utf-8")
            with (patch.object(manager, "FREEWIFI", freewifi),
                  patch.object(manager, "KANA_OUT", kana_output),
                  patch.object(manager, "KANA_STATE", offline_state)):
                cfg = manager.load_config()
                manager.sync_freewifi(cfg)
                manager.validate(cfg)
                projection = manager.parse_m3u(freewifi)
                self.assertIn("youtube.kana_tube", projection)
                self.assertEqual(
                    projection["youtube.kana_tube_iptv"]["url"],
                    manager.KANA_9X_PROXY,
                )
                self.assertIn("配信確認中", projection["youtube.kana_tube"]["ext"])

    def test_kana_main_playlist_is_only_youtube_watch(self):
        import re
        lines = manager.KANA_OUT.read_text(encoding="utf-8").splitlines()
        urls = [line.strip() for line in lines if line.startswith(("https://", "http://"))]
        self.assertEqual(len(urls), 1)
        self.assertRegex(urls[0], r"^https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}$")

    def test_kana_preserves_only_matching_live_unexpired_hls(self):
        import time
        vid = "dD3INnBLoVQ"
        fresh = int(time.time()) + 3600
        stale = int(time.time()) - 120
        origin = "https://manifest.googlevideo.com/api/manifest/hls_playlist"
        url = f"{origin}/expire/{fresh}/id/{vid}.1/itag/96/file/index.m3u8"
        self.assertTrue(manager.kana_hls_still_usable(url, vid))
        self.assertFalse(manager.kana_hls_still_usable(url, "DAmfaJ-bGeg"))
        self.assertFalse(manager.kana_hls_still_usable(
            f"{origin}/expire/{stale}/id/{vid}.1/itag/96/file/index.m3u8", vid))
        self.assertFalse(manager.kana_hls_still_usable(
            f"{origin}/expire/{fresh}/id/{vid}.1/force_finished/1/file/index.m3u8", vid))
        self.assertFalse(manager.kana_hls_still_usable(
            "https://www.youtube.com/watch?v=" + vid, vid))

    def test_search_based_general_channels_have_guards(self):
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        unguarded = [
            item["id"] for item in cfg["general"]
            if not (item.get("page") or "").strip()
            and not (item.get("direct_url") or "").strip()
            and not (item.get("guard_terms") or [])
        ]
        self.assertEqual(unguarded, [])

    def test_general_output_has_only_configured_ids_and_unique_video_ids(self):
        import re
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        allowed = {item["id"] for item in cfg["general"]}
        text = manager.GENERAL_OUT.read_text(encoding="utf-8-sig", errors="replace")
        lines = text.splitlines()
        seen_video = {}
        stale = []
        duplicate = []
        for i, line in enumerate(lines):
            if not line.startswith("#EXTINF:"):
                continue
            m = re.search(r'tvg-id="([^"]+)"', line)
            if not m:
                continue
            channel_id = m.group(1)
            if channel_id not in allowed:
                stale.append(channel_id)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                continue
            key = manager.video_key(lines[j].strip())
            if key.startswith("video:"):
                if key in seen_video:
                    duplicate.append((seen_video[key], channel_id, key))
                else:
                    seen_video[key] = channel_id
        self.assertEqual(stale, [])
        self.assertEqual(duplicate, [])

    def test_volatile_live_sources_are_health_gated(self):
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in cfg["general"]}

        arashiyama = by_id["youtube.arashiyama_monkeypark"]
        self.assertEqual(
            arashiyama.get("page"),
            "https://www.youtube.com/@ArashiyamaMonkeyparkLivecam",
        )
        self.assertTrue(arashiyama.get("guard_terms"))
        self.assertFalse(arashiyama.get("persistent", False))

        for channel_id in (
            "youtube.matsuyama_kankoko",
            "youtube.matsuyama_kankoko_board",
            "youtube.matsuyama_kankoko_exterior",
        ):
            item = by_id[channel_id]
            self.assertEqual(item.get("probe"), "visual")
            self.assertFalse(item.get("persistent", False))


    def test_outputs_are_inside_youtube_v2(self):
        self.assertEqual(manager.GENERAL_OUT.as_posix().split("youtube/")[-1], "output/general.m3u")
        self.assertEqual(manager.KANA_OUT.as_posix().split("youtube/")[-1], "output/kana.m3u")
        self.assertEqual(manager.MANDARIN_OUT.as_posix().split("youtube/")[-1], "output/mandarin.m3u")

    def test_freewifi_has_no_legacy_youtube_logo_paths(self):
        text = Path("freewifi").read_text(encoding="utf-8-sig", errors="replace")
        bad = [
            line for line in text.splitlines()
            if 'tvg-id="youtube.' in line
            and any(x in line for x in ("/logos/youtube/", "/logos/youtube_live/", "/logos/youtube_special/"))
        ]
        self.assertEqual(bad, [])

    def test_active_youtube_entries_use_current_numbered_logos(self):
        text = Path("freewifi").read_text(encoding="utf-8-sig", errors="replace")
        for line in text.splitlines():
            if not line.startswith("#EXTINF:") or 'tvg-id="youtube.' not in line:
                continue
            self.assertIn('tvg-logo="', line)
            self.assertIn("/youtube/logos/", line)
            self.assertNotIn("/logos/youtube", line)

    def test_youtube_logo_files_are_not_duplicate_blobs(self):
        logo_root = Path("youtube/logos")
        seen = {}
        import hashlib
        for path in sorted(logo_root.rglob("*")):
            if not path.is_file():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertNotIn(
                digest,
                seen,
                f"duplicate logo content: {seen.get(digest)} and {path.as_posix()}",
            )
            seen[digest] = path.as_posix()

    def test_rch_and_ehime_catv_do_not_contain_youtube_entries(self):
        text = Path("freewifi").read_text(encoding="utf-8-sig", errors="replace")
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not line.startswith("#EXTINF:"):
                continue
            group = ""
            import re
            m = re.search(r'group-title="([^"]*)"', line)
            if m:
                group = m.group(1)
            if group not in ("Rch", "愛媛CATV"):
                continue
            self.assertNotIn('tvg-id="youtube.', line)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                self.assertNotIn("youtube.com", lines[j].lower())
                self.assertNotIn("youtu.be", lines[j].lower())


if __name__ == "__main__":
    unittest.main()
