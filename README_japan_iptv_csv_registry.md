# 日本IPTV候補DB CSV版（URLなし）

公開GitHub上で確認した日本IPTV候補を **URLなし** で管理する台帳です。
実配信URL、token、vhash、p2p/p5p URLは入れていません。

## ファイル構成（himitsu直下）

```text
japan_iptv_channels.csv          # 本体。チャンネル別の候補台帳
japan_iptv_systems.csv           # 系統DB
japan_iptv_sources.csv           # 根拠ソース一覧
japan_iptv_decision_rules.csv    # A/B/C/Xの判断基準
japan_iptv_search_backlog.csv    # 次に掘る検索ワード
japan_iptv_a_high_priority.csv   # A本命かつ高優先度だけ抜粋
japan_iptv_summary_by_genre.csv  # ジャンル別集計
japan_iptv_filter_candidates.py  # CSV絞り込み補助
```

## まず見るところ

```text
japan_iptv_a_high_priority.csv
```

ここに、次に掘る本命候補だけを抜き出しています。

## 運用ルール

- URLは入れない
- token / vhash / p2p / p5p は記録しない
- 有料CS・NSFW系は採用ではなく候補/保留として扱う
- 公式無料系はテスト対象ではなく参考枠
- 採用判断は A/B/C/X で管理する

## 採用判断

```text
A_本命候補
  複数Gitで確認、slug/IDが一致、系統が明確

B_保留候補
  候補価値はあるが、出現数・鮮度・系統に不安あり

C_資料のみ
  EPG表・チャンネル表だけ。URL系統なし

X_除外
  p2p/p5p、token強め、古すぎ、出所不明など
```

## 次にやること

1. `japan_iptv_a_high_priority.csv` から地方局を優先確認
2. 次にCS映画、アニメ、スポーツ、韓流を確認
3. 同じslug/IDが複数Gitに出ているか確認
4. `decision` と `notes` を更新
5. 採用候補だけ別途M3U生成候補へ回す

## 注意

このDBは調査台帳です。再生支援用のURL集ではありません。
公開GitHub上で見える範囲を、候補管理・分類・EPG整理用にまとめています。
