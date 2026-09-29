# 日本IPTV候補DB 安全運用版

`ajiousama/himitsu` 直下で管理する、URLなしの日本IPTV候補調査台帳です。

## 目的

公開GitHub上で見つかった候補を、再生URL集ではなく、次の観点で整理します。

- 系統分類
- ジャンル分類
- 採用/保留/除外判断
- 次に掘る検索テーマ
- 出現元の記録

## 置いているファイル

```text
README_japan_iptv_safe_registry.md
japan_iptv_research_groups.csv
japan_iptv_channels_template.csv
japan_iptv_systems.csv
japan_iptv_sources.csv
japan_iptv_decision_rules.csv
japan_iptv_search_backlog.csv
japan_iptv_summary_by_genre.csv
japan_iptv_filter_candidates.py
```

## GitHubに置かないもの

以下はGitHubに置きません。

```text
直接再生URL
有料CSのチャンネル別slug一覧
token / vhash
p2p / p5p
DRM/Widevine系の情報
NSFW系の直接識別子
```

## ローカルでだけ持つもの

詳細なチャンネル別候補表は、必要ならローカルファイルとして管理します。GitHubには、カテゴリ単位・系統単位の台帳だけを置きます。

## 次に見るもの

まずは `japan_iptv_research_groups.csv` を見て、地方局・映画CS・アニメ/キッズ・スポーツ/趣味などのグループ単位で追加調査します。
