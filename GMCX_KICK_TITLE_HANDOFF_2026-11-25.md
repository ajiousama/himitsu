# 引継ぎ記録：GCCX／KICK系VODタイトル付け（2026年11月25日）

## 案件名・最終目的
長時間のゲームセンターCX（GCCX）KICK録画を、実映像から正しくゲーム名・番組内容名で案内し、VOD5とFreeWiFiに表示する。最終的な番組単位の正確な開始・終了時刻は別途確証を取る。58分区間はナビゲーション用の**仮チャプター**であり、1区間=1放送回ではない。

## 今回の進捗と検証済み事実
- 2026-11-25、GitHubの現行データ `kick_replay.json` と `VOD5` を再検証。GCCXは5録画・合計144区間、うち最初43区間が「仮チャプター」に逆戻りしていた。
- 原因A：11/24録画 `0ec7d1f0-88cc-44c9-9bac-4b4f8bd302db` に新規10区間。
- 原因B：11/22録画 `511d1d0e-f492-43c5-979b-0653754fcf83` の映像長が約48時間まで延び、未特定26区間。
- 原因C：旧4区間は映像根拠が保存済みなのに、`gmcx_long_nav.py` が `actual_video_shows_subject_but_exact_episode_unverified` を受け付けず未確定化。この判定区分を明示的に追加し、作品タイトルの確定とは分けて「実映像で内容確認」と表示するよう修正。
- GitHub Actions `45564155322` による12シャード×4コマの実映像取得は全ジョブ成功。**新規36区間すべてにゲーム名または内容名を登録。** `gmcx_frame_identified_titles.json` 証拠レコード238件（過去録画のデータも含む）。
- 本番公開コミット `d2087b61d83a4facd2a078a0c21b6c549ffd40a6` でVOD5、vod5/playlist.m3u、freewifiを一括更新。後でGitHubから3ファイルを直接取得して、**144 GCCX区間のうち141がタイトル・内容名付き、3が未特定**、VOD5とミラー完全一致、FreeWiFiの144件の表示名も完全一致を確認。
- 11/24ではクォース、ジョイメカファイト、悪魔城ドラキュラX系アクション、ザ・ハウス・オブ・ザ・デッド、GCCXmini生放送、公式ファンクラブ告知を確認。
- 11/22延長分ではスーパーマリオRPG、がんばれゴエモン2、新・熱血硬派くにおたちの挽歌、MOTHER2、月風魔伝、パックランド、GCCXロケ等を確認。**具体的な作品名が確認できない区間は、確認できたゲームのジャンルや企画内容を使った説明的な見出し**に留めている。

## 未特定の3区間（旧黒画面）
- 11/21録画 `09a837cb-4604-437c-ae57-a75c9a1f536f`、66120秒から。
- 11/19朝録画 `97bb649f-ef37-4e7a-b9c2-d986435f699d`、41760秒から。
- 同 45240秒から。
- 今回の動画抽出でも3区間とも実映像4コマが黒画面。2026-11-23の過去検証では各12コマすべて黒画面だった。**架空のゲーム名・話数を付けない**。従来記録 `gmcx_black_video_unverified_20261123.json` を維持。

## 確定した仕様・指示
- ソースVOD IDとsource_urlの完全一致を確認して命名し、録画間で同じタイトルを連番として流用しない。
- 一部が本編・別ゲーム・たまゲー・宣伝の複数コンテンツにまたがる場合、その事実が分かるタイトルを付ける。
- VOD5は `kick_replay_freewifi.py` と `gmcx_long_nav.py` の再生成対象。今回は事故なく早期反映するためGitHub Git Data APIで3ファイルを単一コミットに同期。元の再生URL・尺・EPG・乃木坂VOD・華奈tubeは変更していない。
- 現在の表示名は実映像に基づく**内容ナビ**。正式な番組話数と正確な秒単位境界は未確定。

## 失敗した方法と再試行不要
- 58分ごとに話数を推定する方法は誤り。固定時間を1話の境界として扱わない。
- 番組内の一部画像だけを正式な放送回タイトルと断定しない。
- 旧証拠のconfidence判定区分を無視して4件が未確定に戻っていた不具合は修正した。
- 多数のYouTube等の自動更新コミットが併走するため、GitHub contents APIがHTTP 409を返した。古いコミットへ強制上書きせず、最新ファイルを再取得して差分を再適用すること。Git Data APIでHEADの期待SHAを守る方式が成功。

## 発見した資料・URL
- 現行VOD5: https://raw.githubusercontent.com/ajiousama/himitsu/main/VOD5
- 最新データ: https://github.com/ajiousama/himitsu/blob/main/gmcx_frame_identified_titles.json
- 公開コミット: https://github.com/ajiousama/himitsu/commit/d2087b61d83a4facd2a078a0c21b6c549ffd40a6
- 最新一括検証: https://github.com/ajiousama/himitsu/actions/runs/45564155322
- 過去の引継ぎ: https://github.com/ajiousama/himitsu/blob/main/GMCX_KICK_TITLE_HANDOFF_2026-11-23.md

## 再発防止・次に実行すべき具体的作業
1. `.github/workflows/gmcx_bulk_title_review.yml` に毎日07:19／19:19 JSTの未確定映像抽出を追加（2026-11-25コミット `7b73bd2123f5bc8c4755a0f14910d9485da2f89d`）。成果物は5日保持。**これは映像収集の自動化であり、ゲーム名の無人確定までできたという意味ではない**。
2. 次回新録画が出たら `VOD5` の仮チャプターを実際のVOD ID/開始秒で列挙し、先に自動採取された4コマ画像を確認。根拠付きで `gmcx_frame_identified_titles.json` に追加。必ずVOD5・FreeWiFi本番反映を後から読み取り確認する。
3. 継続する未特定3区間は、黒以外の画像が確認されたときだけ再命名する。放送本編の正確な境界は今後の別工程。
4. `Update KICK Replay Catalog` の後続自動処理が今回の141件を維持しているかを確認し、旧状態への巻戻しを防止する。
