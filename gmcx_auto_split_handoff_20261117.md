# GCCX KICK自動分割 引継ぎ（2026-11-17 JST）

## 案件名・最終目的
ajiousama/himitsu 内のKICK GCCX録画を、期限切れ前に毎時取得・正確な番組境界で自動分割・ゲーム／番組名を確認してVOD5・FreeWiFiへ同期する。58分は未確認時の暫定ナビ。映像・音声からの秒単位境界を優先。EPG、KanaTube、無関係なFreeWiFi機能を変更しない。

## これまでの作業・進捗
- 既存の kick_replay.py / kick_gmcx_chapters.py / gmcx_long_nav.py / gmcx_unknown_title_probe.py / kick_replay_freewifi.py が毎時の録画取得、暫定58分分割、一部タイトルOCR、VOD5・VOD5互換・FreeWiFi同期を担う。
- 11/16に3日4録画の147境界を音声調査：25音声一致候補、118不一致、4比較不能。音楽一致のみでタイトルや正確な番組境界を確定してはいけない。
- 11/17に gmcx_auto_opening.py、gmcx_auto_opening_scan.py、test_gmcx_auto_opening.py を新設し、gmcx_long_nav.py と .github/workflows/update_kick_replay.yml に組み込んだ。新しい録画から順番に音声一致を探し、独立した参照テンプレートと候補結果を保存。映像確認済み開始点・レミングスＡ〜Ｗ等の連続区間は変更しない。
- 初回新機能Action #563（run 43973924631）は成功。gmcx_opening_fingerprint.json（e4f91158の3480秒付近、別4区間と相互照合した音声数値特徴量のみ）が保存された。gmcx_auto_opening_review.json は新しい78c515faの最初16区間が全てinsufficientで、音声由来の境界補正は現在0件。
- KICK11/15録画78c515faは156451秒と認識され、45区間がVOD5公開。しかし45区間ともゲーム・番組タイトル未特定。現在のVOD5は計135項目（確認時）、うち新しいGCCX録画45区間。
- KICK APIがduration=0の録画もHLSメディアのENDLISTとEXTINF総和から終了済み尺を確認する fallback を kick_replay.py に追加。APIが古くis_live=trueを返してもENDLISTで完了を証明できた場合だけlive解除。test_kick_replay_duration.py に6テスト。最新Actionでの実機確認は未完了。

## 確認済み事実／推測・未確認の区別
- 確認済：初回自動処理のテスト・ジョブ成功、音声数値テンプレート保存、11/15録画の45区間生成、16区間での音声一致候補0。
- 未確認：11/15録画156451秒の復旧が新fallbackによるものかKICK元APIの自然な更新によるものか。fallbackの本番効果はまだ実測していない。
- 新しい11/17開始のc07bc339は直近のkick_replay.jsonでduration=0、is_live=true。実際にライブ中の可能性があり、ENDLISTなしで録画扱いしてはならない。
- KICKアーカイブ消滅によるVOD5項目減少は正常なケースがある。消滅したものの復活や再生成功を確認なしに宣言しない。

## 確定仕様・ユーザー指示
- 消滅前の新録画が最優先。第九・歓喜の歌のオープニング音声と番組ロゴ・ゲーム名映像で分割。違うゲームの登場だけで番組切替とは断定しない。
- 不明な放送回や終了位置を捏造しない。既存の確定映像境界とレミングスＡ〜Ｗを保護。
- EPGとKanaTubeなどの別案件を変更しない。URLを表示する際は完全なhttpsアドレスを個別コードブロックで表示する。

## 資料・URL
毎時ワークフロー：
```text
https://github.com/ajiousama/himitsu/actions/workflows/update_kick_replay.yml
```
初回自動処理成功のジョブ：
```text
https://github.com/ajiousama/himitsu/actions/runs/43973924631
```
直近は #564=43975084084 が進行中、#565=43975256614 が待機中（確認後に再取得が必要）。検証記録：gmcx_all_days_audio_recheck_20261116.json、gmcx_audio_opener_findings_20261116.json、gmcx_vod5_unresolved_audit_20261116.json、gmcx_frame_identified_titles.json、gmcx_exact_boundaries.json。

## 失敗した方法と不要な繰り返し
- 58分ごとの話数を長時間特番の途中まで機械的に加算すると後続が大幅にズレる。繰り返さない。
- KICK APIだけでduration0/is_liveを確定すると録画が公開されない。HLS ENDLISTで検証する。ENDLISTなしに推定録画尺で公開しない。
- 11/15録画の最初16仮分割で、同一音楽を±36秒だけ探す方法は全件insufficient。単純再実行より全時間帯探索など異なる手段が必要。
- 古い録画の有効期限切れを復旧済みとして扱わない。取得可能な新録画を優先。

## 未解決・保留
- 自動音声スキャンは58分境界の±36秒内だけを調べる。長時間特番による数分〜数時間のズレを録画全域から探索する機能は未実装。すべて正確な自動分割が完成したとは言えない。
- 11/15録画45区間のタイトルは未確定。OCRの初回27区間もno_title_match。
- 11/17録画c07bc339の録画終了と公開、HLS duration fallbackの実動作と最新追加テスト合否は未確認。
- 11/13に音声で見つかった通常回開始候補の約26〜29秒差、長時間SP終了位置も映像ではまだ確定していない。

## 次に実行すべき具体的作業
1. GitHub Actions #564 / #565 の現在の結論・ログ確認。test_kick_replay_duration.py の合否、GCCX_DURATION_FROM_COMPLETED_HLSの実行ログ確認。
2. 最新kick_replay.jsonでc07bc339が終了録画になっているか、最新VOD5の全件数・GCCX分割・FreeWiFi互換一致を検証。
3. 11/15の16件insufficientを反復せず、保存済み音声指紋を使い録画全体の10分前後の時間窓をスキャンして正規のオープニング候補を探す。最初は読み取り専用で検証後、厳格な閾値・映像確認とともに自動分割へ導入。
4. 新録画のロゴ画面・ゲーム名抽出OCRを改良して実タイトルと境界を結び付ける。映像未確認なら候補と明記。
5. 再生URLのギャップ／重複／最大再生秒数、確認済み境界の保護、全プレイリスト一致を自動テストで担保。未実施を完了済みと報告しない。
