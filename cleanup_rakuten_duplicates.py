from pathlib import Path

P = Path("freewifi")

# For these duplicated Rakuten channels, keep the parameterized (B) entry and
# remove only the plain playlist URL entry. Single-entry Rakuten channels are untouched.
PLAIN_URLS = {
    "https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-rchannelmensnecohlscmaf-rakutenjp/playlist.m3u8",
    "https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-gravurecmaf-rakutenjp/playlist.m3u8",
    "https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-shigekicmaf-rakutenjp/playlist.m3u8",
}


def main() -> None:
    text = P.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    out = []
    removed = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF:") and i + 1 < len(lines) and lines[i + 1].strip() in PLAIN_URLS:
            removed.append(lines[i + 1].strip())
            i += 2
            if i < len(lines) and lines[i] == "":
                i += 1
            continue
        out.append(lines[i])
        i += 1

    P.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
    print(f"Rakuten duplicate cleanup: removed {len(removed)} plain entries")
    for url in removed:
        print(f"  removed: {url}")


if __name__ == "__main__":
    main()
