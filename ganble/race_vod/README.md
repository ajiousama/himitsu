# 競輪・地方競馬 レースVOD（EPGベース）

2026-11-20 初期実装。**独立システム**。既存のFreeWiFi、yovi、EPG、BOAT・AUTO・JRA・KICKには触れない。

- 対象：競輪 (keirin.*) と地方競馬 (chihou.*) のみ。
- 入力：既存の public_sports_epg_local.xml。「【ＮＲ】 H:MM発走」というレース枠だけ取り込む。
- 出力：catalog.json（日付・開催場・R、45日保持）、playlist.m3u（**直再生確認済みURLだけ**）。
- UI：index.html で日付・場・R別に探せる。未確認映像は公式検索ページへのリンクのみ。
- 競輪の映像元候補：TIPSTAR。地方競馬の映像元候補：楽天競馬。
- **アーカイブ映像の存在と外部再生可能な直リンクは別**。未確認のm3u8を推測・合成して載せない。認証・DRM・アクセス制限を回避しない。

## 開発・動作確認

リポジトリのルートから：

~~~shell
python -m unittest -v ganble.race_vod.test_build
python ganble/race_vod/build.py
python -m http.server 8080
~~~

ブラウザで http://localhost:8080/ganble/race_vod/index.html を表示。GitHubのファイル表示画面はWebホスティングではない。一般公開するには別途静的ホストが必要。

update_race_vod.yml は30分ごとに既存EPGを取り込み、catalog.json と playlist.m3u だけを更新する。過去45日間のレース情報を保つ。EPGに存在しない開催・中止・延期を推測して追加しない。表示件数と映像再生成功件数は別。

## 外部再生の検証が完了したら

許可された映像について、実際の映像・音声・レースの一致・有効期限を確認してから verified_sources.json に登録する。

~~~json
{
  "keirin:20261120:keirin.kokura:01": {
    "url": "https://example.org/authorized-recording.m3u8",
    "playback_verified": true
  }
}
~~~

これは**ダミーURL**であり、実際には登録しない。確認できないレースは not_verified のままで、M3Uに入らない。

## 公式情報

- TIPSTARは2026年10月の案内でレースアーカイブをアプリ内限定と記載。外部直再生は未確認：
  https://about.tipstar.com/news/20261014_66/
- 楽天競馬のレース映像ガイド：
  https://keiba.rakuten.co.jp/guide/howto/live_movie
- 楽天競馬の過去映像日付検索：
  https://keiba.rakuten.co.jp/archivemovie/searchDate
