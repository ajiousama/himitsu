from pathlib import Path
import re

# Permanent fix: the current-venue updater must not prune unrelated FreeWiFi entries.
sp = Path('freewifi_today_public_sports.py')
s = sp.read_text(encoding='utf-8-sig')
s2 = re.sub(
    r'\n\ndef prune_abema_rakuten\(text\):.*?(?=\n\ndef replace_block\(text,block\):)',
    '',
    s,
    count=1,
    flags=re.S,
)
s2 = s2.replace(
    "base=prune_abema_rakuten(FREEWIFI.read_text(encoding='utf-8-sig',errors='replace'))",
    "base=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace')",
    1,
)
if s2 == s:
    raise SystemExit('Expected obsolete Rakuten pruning code was not changed')
if 'prune_abema_rakuten' in s2:
    raise SystemExit('Obsolete Rakuten pruning code still remains')
sp.write_text(s2, encoding='utf-8')

# Restore the complete user-selected Rakuten section without duplicating entries.
fp = Path('freewifi')
f = fp.read_text(encoding='utf-8-sig')
rakuten = '''## Rakuten-JP

#EXTINF:-1 tvg-id="rch_30" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/186_traintravel.png" group-title="Rakuten-JP",鉄道・旅
https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-tandtcmaf-rakutenjp/playlist.m3u8

#EXTINF:-1 tvg-id="rch_98" tvg-name="セクシーエンタメチャンネル" tvg-logo="https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/239_sexyenterme.png" group-title="Rakuten-JP",セクシーエンタメチャンネル
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
'''
pat = re.compile(r'## Rakuten-JP\n.*?(?=## 今日の開催場)', re.S)
if not pat.search(f):
    raise SystemExit('Rakuten section anchor missing')
f = pat.sub(rakuten + '\n', f, count=1)
fp.write_text(f, encoding='utf-8')

# Validate exact intended counts.
checks = {
    'rch_30': 1,
    'rch_98': 1,
    'rch_59': 2,
    'rch_41': 2,
    'rch_40': 2,
    'rch_42': 1,
}
out = fp.read_text(encoding='utf-8')
for cid, expected in checks.items():
    actual = out.count(f'tvg-id="{cid}"')
    if actual != expected:
        raise SystemExit(f'{cid}: expected {expected}, got {actual}')
print('Rakuten restored and obsolete pruning removed')
