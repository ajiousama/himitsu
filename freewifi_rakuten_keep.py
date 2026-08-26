from pathlib import Path
import re

FREEWIFI = Path('freewifi')
START = '# === RAKUTEN_KEEP_START ==='
END = '# === RAKUTEN_KEEP_END ==='

BLOCK = '''# === RAKUTEN_KEEP_START ===
## Rakuten TV（鉄道・アダルトのみ）

#EXTINF:-1 tvg-id="rch_30" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/186_traintravel.png" group-title="Rakuten-JP",鉄道・旅
https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-tandtcmaf-rakutenjp/playlist.m3u8

#EXTINF:-1 tvg-id="rch_30" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/186_traintravel.png" group-title="Rakuten-JP",鉄道・旅 (B)
https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-tandtcmaf-rakutenjp/playlist.m3u8?ads.uuid=79f6c984-2f32-573c-a7ff-a13644466ce4&ads.device_make=rchweb&ads.refid=0&ads.url=channel.rakuten.co.jp&ads.uid_ss=&ads.uid_rch=79f6c984-2f32-573c-a7ff-a13644466ce4

#EXTINF:-1 tvg-id="rch_98" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/239_sexyenterme.png" group-title="Rakuten-JP",セクシーエンタメチャンネル
https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-rvariety-cmaf-rakutenjp/playlist.m3u8

#EXTINF:-1 tvg-id="rch_59" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/240_mensneco.png" group-title="Rakuten-JP",おとなの歓楽街 by MEN'S NECO
https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-rchannelmensnecohlscmaf-rakutenjp/playlist.m3u8

#EXTINF:-1 tvg-id="rch_59" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/240_mensneco.png" group-title="Rakuten-JP",おとなの歓楽街 by MEN'S NECO (B)
https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-rchannelmensnecohlscmaf-rakutenjp/playlist.m3u8?ads.uuid=79f6c984-2f32-573c-a7ff-a13644466ce4&ads.device_make=rchweb&ads.refid=0&ads.url=channel.rakuten.co.jp&ads.uid_ss=&ads.uid_rch=79f6c984-2f32-573c-a7ff-a13644466ce4

#EXTINF:-1 tvg-id="rch_41" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/241_gravure.png" group-title="Rakuten-JP",アイドル・グラビア
https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-gravurecmaf-rakutenjp/playlist.m3u8

#EXTINF:-1 tvg-id="rch_41" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/241_gravure.png" group-title="Rakuten-JP",アイドル・グラビア (B)
https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-gravurecmaf-rakutenjp/playlist.m3u8?ads.uuid=79f6c984-2f32-573c-a7ff-a13644466ce4&ads.device_make=rchweb&ads.refid=0&ads.url=channel.rakuten.co.jp&ads.uid_ss=&ads.uid_rch=79f6c984-2f32-573c-a7ff-a13644466ce4

#EXTINF:-1 tvg-id="rch_40" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/242_shigekistrong.png" group-title="Rakuten-JP",刺激ストロング
https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-shigekicmaf-rakutenjp/playlist.m3u8

#EXTINF:-1 tvg-id="rch_40" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/242_shigekistrong.png" group-title="Rakuten-JP",刺激ストロング (B)
https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-shigekicmaf-rakutenjp/playlist.m3u8?ads.uuid=79f6c984-2f32-573c-a7ff-a13644466ce4&ads.device_make=rchweb&ads.refid=0&ads.url=channel.rakuten.co.jp&ads.uid_ss=&ads.uid_rch=79f6c984-2f32-573c-a7ff-a13644466ce4

#EXTINF:-1 tvg-id="rch_42" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/243_r-15movie.png" group-title="Rakuten-JP",映画 (R15+)
https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-movie2cmaf-rakutenjp/playlist.m3u8
# === RAKUTEN_KEEP_END ==='''


def main():
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S)

    # Remove any legacy Rakuten-JP entries so only the requested categories remain.
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and 'group-title="Rakuten-JP"' in line:
            i += 2
            if i < len(lines) and lines[i] == '':
                i += 1
            continue
        out.append(line)
        i += 1
    text = '\n'.join(out).rstrip() + '\n'

    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    if anchor in text:
        text = text.replace(anchor, BLOCK + '\n\n' + anchor, 1)
    else:
        text = text.rstrip() + '\n\n' + BLOCK + '\n'

    FREEWIFI.write_text(text, encoding='utf-8')
    print('Rakuten keep block applied: rail + adult only')


if __name__ == '__main__':
    main()
