# BOAT Auto v4

## 2026-09-08の再構成

対象は `ajiousama/himitsu` の FreeWiFi。外部の `earphone1981/public-sports-iptv` は更新元にしない。

今日確認した問題:

- 5分cronを設定していても実際のActions実行履歴には数十分～数時間の空白があった。同じcron基盤のwatchdogだけでは埋められない。
- URL取得のみで正常判定し、音声・映像の再生確認がなかった。
- 取得済みURLも毎回取り直していた。
- 全体EPG更新が過去のスナップショットを最新mainへコピーし、BOATのEPGを巻き戻す可能性があった。

## 所有者と実行

- `update_boat_auto.yml` → `boat_worker.py` が唯一のBOAT取得・状態公開処理。
- workerは最大5時間30分稼働し、各サイクルの開始間隔を原則60秒にする。通信・検証処理が60秒を超えた場合は完了後に次へ進む。
- 終了30分前に `workflow_dispatch` で次のworkerをキューに登録。重複起動は待機し、稼働中workerをキャンセルしない。
- 毎時17分のcronと既存watchdogは、worker自体が止まった場合の再起動経路。取得間隔をcronに依存させない。
- `boat_worker_status.json` に実行ID・公開時刻・サイクル数・後続起動状態を記録。
- Actions障害や配信元障害、プレイヤーの一覧キャッシュまで含めた「100%開始保証」はできない。開始前成功は次回の実配信で判定する。

## 各場の取得

- 公式開催表・各場の12R分の時刻を取得。公式が失敗した場合のみJSONミラーへ切り替える。当日の確認済み開催表を保持し、通信失敗や一時的な場の消失で消さない。
- 開催表は15分ごと、各場の配信取得は1R150分前から。モーニング・デイ・ナイターを同一処理で扱う。
- Vercelの既存取得口と公式Playback APIを使用。手動SEEDファイルは読まない。
- 当日・場ID確認 → live HLSとメディア断片確認 → ffmpegで映像と音声を1秒デコードして初回成功とする。
- `first_verified_at` / `ready_before_first_race` で開始前確認の実績を残す。`visible_count` は表示数であり、再生確認数ではない。
- 成功済みURLは保持。5分ごとの再生監視で異常があれば次の分に再確認し、連続失敗時に自動再取得する。期限切れも自動再取得対象。
- 別場URL重複、前日URL、トークン期限の巻き戻り、VODのENDLIST、メディア停止・巻き戻り、音声/映像デコード失敗は正常扱いしない。
- 各場1R30分前の未確認は `boat_auto_alert.json` で自動復旧中とする。手動ボタンを押す指示にはしない。
- 終了した場は当日中保持。正常確認後に更新時刻が古いだけでは配信異常扱いしない。

## EPG・公開

- 各Rの時刻とR番号を表示し、時刻の3分後に次へ切り替える。公式の時刻は締切予定時刻を含む。
- 最終R後は「本日の開催は終了しました」。次の予定は「翌日」「次回」と明記する。次回予定がなければ終了表示を日付変更まで継続。
- `boat_publish.py` は最新mainの非BOAT内容を保持したまま、BOATブロックとEPGだけを再適用する。
- 全体EPG更新にも同じ再適用処理を追加。公開前に日付、URL重複、番組数、番組重複/重なりを検査する。
- 外部消費側との互換性のため `system: boat-auto-v3` と既存JSONファイル名・`seed_required` キーを維持。v4は `architecture_version: 4` で識別する。`seed_required` は現在「再生未確認」を表す互換キー。

## 整理

削除: `boat_stream_seed.m3u`、過去コミットへ処理を戻す一度限りの `repair_public_sports_sync_once.py` と `repair_epg_pipeline_once.yml`。
旧BOAT単発cron処理・毎回URL再取得・手動SEED要求を置き換えた。他競技にも使うiPhone用スクリプトは残す。

## 検証

`python -m unittest -v test_boat_auto_system test_boat_reliability`

日付変更、同日キャッシュ保持、全12R、他競技EPG保持、終了後表示、音声/映像未確認拒否、別場URL拒否、成功URL固定、連続失敗復旧を検証する。
実際の開始前成功は、各開催場の `first_verified_at` と `ready_before_first_race` を確認する。単なるworkflowの緑表示を開始成功と見なさない。

GitHubの定期実行の制約: https://docs.github.com/actions/using-workflows/events-that-trigger-workflows#schedule
