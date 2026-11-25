#!/usr/bin/env python3
"""Read-only probe of a public official race player. No publishing or bypass.
Only explicit HTML video/source URLs are tried. A JS-only player is reported
as unresolved; no guessed paths, authentication, cookies, or custom referrers.
"""
import json
import subprocess
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

PAGE = "https://keiba-lv-st.jp/movie/player?date=20261125&race=1&track=sonoda"

class Media(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = []
    def handle_starttag(self, tag, attrs):
        if tag not in ("video", "source"):
            return
        a = dict(attrs)
        if a.get("src"):
            self.urls.append(a["src"])

def public_media(page, html):
    p = Media()
    p.feed(html)
    found = []
    for value in p.urls:
        url = urljoin(page, value)
        u = urlsplit(url)
        if u.scheme == "https" and u.hostname and not u.username and not u.password and not u.query and u.path.lower().endswith((".m3u8", ".mp4")):
            if url not in found:
                found.append(url)
    return found

def main():
    result = {"race_id": "nar:20261125:chihou.sonoda:01",
              "page": PAGE, "publication": "none", "candidates": []}
    try:
        with urlopen(Request(PAGE), timeout=20) as f:
            result["http_status"] = f.status
            result["frame_policy"] = f.headers.get("X-Frame-Options")
            result["content_security_policy"] = f.headers.get("Content-Security-Policy")
            html = f.read(2_000_000).decode("utf-8", "replace")
            urls = public_media(f.url, html)
        for url in urls:
            item = {"url": url, "video_and_audio_decoded": False}
            try:
                with urlopen(Request(url, headers={"Origin": "null"}), timeout=15) as f:
                    item["cors"] = f.headers.get("Access-Control-Allow-Origin")
                p = subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", url,
                                    "-t", "5", "-map", "0:v:0", "-map", "0:a:0",
                                    "-f", "null", "-"], capture_output=True, timeout=35)
                item["video_and_audio_decoded"] = p.returncode == 0
                item["error"] = p.stderr.decode("utf-8", "replace")[-400:]
            except Exception as exc:
                item["error"] = str(exc)
            result["candidates"].append(item)
        result["status"] = "candidate_detected" if urls else "no_explicit_public_media_tag"
    except Exception as exc:
        result["status"] = "network_or_page_error"
        result["error"] = str(exc)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
