from pathlib import Path
import re

FREEWIFI = Path('freewifi')
START = '# === RAKUTEN_KEEP_START ==='
END = '# === RAKUTEN_KEEP_END ==='

CHANNELS = [
('rch_47','104_ntvnews.png','日テレNEWS','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-news1hlscmaf-rakutenjp/playlist.m3u8'),
('rch_108','105_fnn.png','FNNプライムオンライン','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-news4-cmaf-rakutenjp/playlist.m3u8'),
('rch_115','106_mbs.png','MBS ニュース','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-news5-cmaf-rakutenjp/playlist.m3u8'),
('rch_45','107_whethernews.png','ウェザーニュース LIVE','https://rch01e-alive-hls.akamaized.net/38fb45b25cdb05a1/out/v1/4e907bfabc684a1dae10df8431a84d21/index.m3u8'),
('rch_88','108_mx.png','TOKYOMX チャンネル','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-tokyomx-cmaf-rakutenjp/playlist.m3u8'),
('rch_56','109_kyodo.png','共同通信News','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-news3hlscmaf-rakutenjp/playlist.m3u8'),
('rch_101','110_ntvnewsselect.png','日テレNEWSセレクト','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-ntv-newsselect-cmaf-rakutenjp/playlist.m3u8'),
('rch_54','111_oriconnews_02.png','オリコンニュース','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-news2cmafhls-rakutenjp/playlist.m3u8'),
('rch_83','112_stockvoice.png','STOCK VOICE','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-stockvoice-cmaf-rakutenjp/playlist.m3u8'),
('rch_103','113_NewsWorld.png','Newsworld (Japan Sub)','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01076-lightningintern-newsworld-rakutenjp/playlist.m3u8'),
('rch_70','114_bloombergtv.png','Bloomberg TV+','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01601-bloomberg-bloombergplus-hls-rakutenjp/playlist.m3u8'),
('rch_90','115_euronews.png','ユーロニュース','https://cdn-apne1.tsv2.amagi.tv/linear/amg00882-euronewssa-euronewsengjp-rakutenjp/playlist.m3u8'),
('rch_102','116_qvc.png','QVC Japan','https://d1flvb4iqlercm.cloudfront.net/r-channel/live.m3u8'),
('rch_112','117_gstv.png','GSTV（宝石専門 CH)','https://rch01e-alive-hls.akamaized.net/15bcd044c531aa99/out/v1/339db39dc83c421f94a8cebb777e4d02/index.m3u8?ads.device_make=rchweb&ads.url=channel.rakuten.co.jp&ads.uuid=4f6cea7e-b66a-5dcf-bd84-86c4eda86ddd&ads.uid_rch=4f6cea7e-b66a-5dcf-bd84-86c4eda86ddd&ads.refid=0'),
('rch_89','119_top-barca.png','TOP BARÇA','https://cdn-apne1.tsv2.amagi.tv/linear/amg17560-fcbarcelona-fcbenglishcmag-rakutenjp/playlist.m3u8'),
('rch_75','123_golf.png','ゴルフ','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-fitness-cmaf1-rakutenjp/playlist.m3u8'),
('rch_97','124_ntvprowrestling.png','日ﾃﾚﾌﾟﾛﾚｽ ｱｰｶｲ部','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-ntv-pro-wrestling-hls-rakutenjp/playlist.m3u8'),
('rch_49','126_skya.png','スカイ A - サプリ','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-skyacmaf-rakutenjp/playlist.m3u8'),
('rch_51','130_gaorazero.png','GAORA ZERO','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-gaorahlscmaf-rakutenjp/playlist.m3u8'),
('rch_64','133_fueltv.png','FUELTV','https://cdn-apne1.tsv2.amagi.tv/linear/amg01074-fueltv-fueltvjpcmaf-rakutenjp/playlist.m3u8'),
('rch_73','142_tezukapro.png','手塚プロダクションTV','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-anime5-cmaf-rakutenjp/playlist.m3u8'),
('rch_65','150_kids.png','キッズ','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-kids-english-cmaf-rakutenjp/playlist.m3u8'),
('rch_34','170_moviedratv.png','ムビドラTV','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-moviecmaf-rakutenjp/playlist.m3u8'),
('rch_43','180_history.png','HISTORY CHANNEL','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-historycmaf-rakutenjp/playlist.m3u8'),
('rch_30','186_traintravel.png','鉄道・旅','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-tandtcmaf-rakutenjp/playlist.m3u8'),
('rch_86','192_wannyan.png','ワンニャンチャンネル','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-pet-cmaf-rakutenjp/playlist.m3u8'),
('rch_113','196_game.png','ぷれいば！～ゲーム専門チャンネル～','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-game-cmaf-rakutenjp/playlist.m3u8?ads.device_make=rchweb&ads.url=channel.rakuten.co.jp&ads.uuid=4f6cea7e-b66a-5dcf-bd84-86c4eda86ddd&ads.uid_rch=4f6cea7e-b66a-5dcf-bd84-86c4eda86ddd&ads.refid=0&ads.rch_hid=&ads.rch_rp=2b325b2f3c87694f9df2c364de7690edd9371221'),
('rch_46','198_fishing.png','釣り','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-fishinghlscmaf-rakutenjp/playlist.m3u8'),
('rch_100','204_igoshogi.png','囲碁・将棋ライト','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-igo-shogi-cmaf-rakutenjp/playlist.m3u8'),
('rch_36','205_shogi.png','将棋','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-shogicmaf-rakutenjp/playlist.m3u8'),
('rch_74','206_mahjong.png','麻雀','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-mahjong-cmaf1-rakutenjp/playlist.m3u8'),
('rch_35','207_pachislo.png','パチンコ・パチスロ','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-pachislocmaf-rakutenjp/playlist.m3u8'),
('rch_37','218_entermeitele.png','エンタメ～テレ DEEP','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-nagoyanextcmaf-rakutenjp/playlist.m3u8'),
('rch_104','227_thats_70s.png',"That's 70s",'https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01076-lightningintern-lightningnow70s-rakutenjp/playlist.m3u8'),
('rch_105','228_thats_80s.png',"That's 80s",'https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01076-lightningintern-lightningnow80s-rakutenjp/playlist.m3u8'),
('rch_106','229_thats_90s00s.png',"That's 90s & 00s",'https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01076-lightningintern-lightning-now90s00s-rakutenjp/playlist.m3u8'),
('rch_107','230_thats_rock.png',"That's ROCK",'https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01076-lightningintern-lightningnowrock-rakutenjp/playlist.m3u8'),
('rch_85','232_enka.png','演歌・歌謡','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-enka-cmaf-rakutenjp/playlist.m3u8'),
('rch_98','239_sexyenterme.png','セクシーエンタメチャンネル','https://cdn-uw2-prod.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-rvariety-cmaf-rakutenjp/playlist.m3u8'),
('rch_59','240_mensneco.png',"おとなの歓楽街 by MEN'S NECO",'https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-rchannelmensnecohlscmaf-rakutenjp/playlist.m3u8'),
('rch_41','241_gravure.png','アイドル・グラビア','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-gravurecmaf-rakutenjp/playlist.m3u8'),
('rch_40','242_shigekistrong.png','刺激ストロング','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-shigekicmaf-rakutenjp/playlist.m3u8'),
('rch_42','243_r-15movie.png','映画 (R15+)','https://cdn-apne1.tsv2.amagi.tv/linear/amg01287-rakutentvjapan-movie2cmaf-rakutenjp/playlist.m3u8'),
]

def build_block():
    out=[START,'## Rakuten TV（履歴から全復活）']
    base='https://channel.rakuten.co.jp/service/img/logo/chlogo-with-number/'
    for tvg,logo,name,url in CHANNELS:
        out.append(f'#EXTINF:-1 tvg-id="{tvg}" tvg-logo="{base}{logo}" group-title="Rakuten-JP",{name}')
        out.append(url)
        out.append('')
    out.append(END)
    return '\n'.join(out)

def main():
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    text = re.sub(re.escape(START)+r'.*?'+re.escape(END)+r'\n?', '', text, flags=re.S)
    lines=text.splitlines(); out=[]; i=0
    while i < len(lines):
        if lines[i].startswith('#EXTINF:') and 'group-title="Rakuten-JP"' in lines[i]:
            i += 2
            if i < len(lines) and lines[i] == '': i += 1
            continue
        out.append(lines[i]); i += 1
    text='\n'.join(out).rstrip()+'\n'
    anchor='# === GENERAL_YOUTUBE_MANAGED_START ==='
    block=build_block()
    if anchor in text: text=text.replace(anchor, block+'\n\n'+anchor, 1)
    else: text=text.rstrip()+'\n\n'+block+'\n'
    FREEWIFI.write_text(text, encoding='utf-8')
    print(f'Rakuten restored: {len(CHANNELS)} channels')

if __name__ == '__main__':
    main()
