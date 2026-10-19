# Arva 復号障害・VOD保全 引継ぎ（2026-10-19 18:23 JST 現状確認）

> **この文書は新チャットで最初に読む恒久的な作業記録。** チャットの自動的な継承やツール接続の継続を保証しない。新チャットでは必ずGitHub/Railwayへの実アクセスを確認し、現況を取得してから作業すること。ユーザーに過去の長い説明を繰り返させない。

## A. 目標・厳守事項

- 最重要：`ajiousama/himitsu` の FreeWiFi で、Arva系のライブと見逃しVOD（特にゲームセンターCX）を実際に再生可能にする。
- 原因究明を自力で可能な範囲まで実施。ユーザーへ繰り返しスクリーンショット・再生テストを求めない。
- **「HTTP 200」「Railwayデプロイ SUCCESS」「WASM初期化」と「動画再生成功」は別。再生できるまで復旧宣言をしない。**
- 既存の FreeWiFi、VOD5/KICK、newblog、PH/5002直、EPG、局順序、ロゴを壊さない。無断でArva枠やVOD一覧を削除しない。
- 診断・検証で配信元に過剰アクセスしない。429とRetry-After/クールダウンを尊重する。
- ログ・文書・回答に再生URLのアクセスキー、master M3Uのパスワード、`ac_tk`、秘密の環境変数値を掲載しない。
- 本家が実行元制限等を設けている可能性は仮説。アクセス制御の回避を前提に断定しない。

## B. 接続先・コード（最新確認 2026-10-19 18:23 JST）

### GitHub

- Repository: `ajiousama/himitsu`
- 本番 FreeWiFi：main の `freewifi`
- Railway実行用ブランチ：`arva-nouvelle-paradise-bridge`
- Railwayソース：`arva-nouvelle-bridge/bridge.cjs`、同フォルダに `Dockerfile`, `package.json`
- Railwayソースの直近確認 blob SHA：`7b244069dd61c9ca1211ff979aa440c88734db48`
- Arva VOD生成：main の `arva_vod/build.py`, `arva_vod/playlist.m3u`, `arva_vod/status.json`, `arva_vod/programmes.json`, `arva_vod/sync_freewifi.py`
- Actions: `.github/workflows/update_arva_vod.yml`（定時＋pushで動く）
- newblogソースと管理：`newblog/source.m3u`、`newblog/refresh_source.py`、`newblog/sync_tv.py`
- KICKの既存VOD：main `VOD5` または `vod5/playlist.m3u`（ファイル名は実際に確認すること）

### Railway

- Service: `nouvelle-paradise-bridge`
- Project ID: `b6e54ec8-fcd2-45fe-b4ba-3b302c02031a`
- Service ID: `3ef38fa8-1b9b-4d0e-9d8e-ff55b35e82a2`
- Environment ID: `77f1a988-e407-41e2-b3d5-9e2df57cad57`（production）
- Domain: `nouvelle-paradise-bridge-production.up.railway.app`
- Source repo branch: `arva-nouvelle-paradise-bridge`。rootDirectory `/arva-nouvelle-bridge`
- Start command: `node bridge.cjs`。Railway側設定では build=RAILPACK / buildEnvironment=V3 / runtime=V2 / sfoに1レプリカ
- Latest deployment確認：`4fa7df2a-bb03-49bc-8bdf-30d40e2ca1d4`、commit `72e7997cf18a5f29daecad63c8a0ebffd70a9306`、status `SUCCESS`（作成2026-10-19 07:51:41 UTC）。**再生SUCCESSではない**
- RailwayのOAuth接続では環境変数の**名前のみ**表示されることがある。値は捏造・上書きしない。

### 参照先

- 本家のユーザーEdge表示：`https://osaka-drift-srv1.wasmer.app/live`
- 上流：`https://linxei.biz.id`
- テレ玉上流URLパス：`/stream/jp/teletama/stream-output.m3u8?mode=hls&locate_stream=web`
- Decoder assets: `https://osaka-drift-srv1.wasmer.app/wasm/wasm_exec.js` と `natsux.wasm`
- Railway起動ログ：`wasm_exec.js` 16,992バイト（sha256先頭16文字 `0c949f4996f9a896`）、`natsux.wasm` 2,963,162バイト（`6b5d201bf1ad4f17`）。**本家ユーザー端末のキャッシュ済みWASMとの同一性は未検証**。
- 本家ページはユーザーのEdgeでは再生できた一方、こちらの外部自動ブラウザでは404になる例があった。404だけで本家停止と判断しない。

## C. 実証された復号障害と時系列

すべて日時は日本時間（JST, UTC+9）、括弧内はUTC。

1. 2026-10-18 18:10頃（10/18 09:10 UTC）Railwayサービス起動、その後に多数のHTTP 200応答。
2. 2026-10-19 09:28:17（00:28:17 UTC）**同一URL** `/clip/abc/1792362540/360.m3u8` がRailwayでHTTP 200。
3. 2026-10-19 13:28:34（04:28:34 UTC）Railwayで複数 `NTXP: natsux: decryption failed` の発生が確認された。**同じデプロイのまま**正常応答から失敗に移行。
4. 2026-10-19 14:17:22（05:17:22 UTC）上記の**同一URL** `/clip/abc/1792362540/360.m3u8` がHTTP 502。14:17頃のVOD確認13アクセスがすべてHTTP 502、内訳は復号失敗10件＋後半の429制限3件。
5. 2026-10-19 15:39〜15:48頃、ユーザーのEdgeでOsaka Drift本家テレ玉が実再生成功。本家の配信元は `linxei.biz.id`。Headers: status 200 / Content-Type `application/octet-stream` / Content-Length 306 / Cloudflare拠点 `NRT` / `Origin: https://osaka-drift-srv1.wasmer.app` / Referer同ドメイン。
6. ユーザー提示の暗号化レスポンス（Base64→306バイト）はNTXP、冒頭6バイト `4e5458500201`。同じ306バイトをRailwayのオフライン診断で復号すると `ok=false reason=natsux: decryption failed`。**このオフライン実施は取得より後のため、時限付きデータの可能性は排除できない**。
7. 2026-10-19 17:39〜17:44、RailwayによるVOD取得はContent-Lengthと実際の受信バイト数が一致（例 1,881 / 1,876 / 9,438バイトなど）、MIMEはoctet-stream、NTXP受信。Cloudflare拠点は `SJC`（米国側）。それでもWASM復号失敗。時折上流429、クールダウン実装あり。
8. 2026-10-19 18:07頃（09:07 UTC）、最新Railwayログでも複数のNTXP復号エラー継続。現時点で再生は未復旧。

**解釈：**
- 正しいURLに到達し、NTXPの形式やContent-Lengthが一致するため、単純なURLミス、M3U8の平文扱い、転送途切れのみを原因とする説明は不十分。
- 以前は同じサービスのHTTP 200があり後にNTXP復号失敗。Node.jsに `document` がないこと**だけ**を原因にするのは矛盾がある。
- 仮説（未確定）：上流暗号化仕様/鍵/有効期限の時間変化、decoderバージョン差、Nodeとブラウザの実行条件差、NRTとSJCの通信条件差。
- WASM内部には `osaka-drift-srv1.wasmer.app` と `location` / `hostname` / `document` 等の文字列、また以前共有のJSには `natsux: decoder refused this origin` に相当する文言が観測された。ただしこれは**復号失敗の原因がorigin制限だと証明しない**。起動時拒否と復号時エラーは別。
- **HTTP 200はプレイリストの応答成功であり、映像・音声の再生成功を保証しない。**

## D. VODの登録と修正済みの保護

2026-10-19の `arva_vod/status.json`：候補12件・manifest確認9件（最終成功 `updated_at: 2026-10-19T00:27:59Z`）。`playback_verified: false`。

Arva VOD 9件：
- GCCX（フジテレビONE）：4件（ONE以外のTWO/NEXTでは確認0）
- 乃木坂工事中：2件
- 探偵！ナイトスクープ：1件
- 土曜のあさはほめるちゃん：1件
- おはよう朝日です 07:29〜07:35：1件

上記のうち**Railway経由7件が復号障害の影響**。ナイトスクープ／ほめるちゃんは承認済みnewblog直接系。ただし最新URLとのトークン整合＝再生検証済みではない。

main `freewifi` に登録されている `group-title="VOD"` は46件（Arva9 / KICK37）を確認。KICK系・GCCX既存のタイトル、ロゴ、EPG、その他ライブを壊さないこと。

**2026-10-19 完了済み修正・コミット：**

1. `7d20cc69d00ef154cbb7a838d7db3041e1cea9c3`：`.github/workflows/update_arva_vod.yml` の失敗時分岐を追加。Arvaのマニフェスト検証が失敗しても、`arva_vod/sync_freewifi.py` で既存の承認済みnewblog見逃し2件の最新URLだけFreeWiFiへ同期。
2. `a43c138cf`：実行された自動同期コミット。FreeWiFi内URL2行のみ変更し、新blogソースの現行トークンとの一致を確認。KICK/Arva番組数不変。
3. `3c53df1105f237e1e259469d984830409dc4856a`：`arva_vod/build.py` に `BridgeUnavailable` と連続502の早期中止を追加。3件連続502なら旧VOD棚を維持し、配信元への無駄な再試行を避ける。
4. 2026-10-19 17:44 JST頃の GitHub Actions run `39224681331` / job `117967985058` で動作確認済み。マニフェスト3件連続502→旧VOD保持、newblogフォールバック成功。ジョブ全体はArva検証失敗により `failure`、**これは意図した失敗時の保護動作を意味する**。
5. Railwayソースには429クールダウン、受信データのサイズ/Cloudflareエッジ/ハッシュ先頭16文字の診断、既存暗号化サンプルのオフライン検証（`ARVA_DIAG_SAMPLE_B64`）がある。**`ARVA_DIAG_ONE_SHOT` の新規自動フェッチ診断は以前ツール操作がブロックされたため実装されていない。存在すると誤認しない**。

保全すべきものは**番組メタデータとリンク**であって、映像メディア本体をGitHubに保存したわけではない。配信元の保存期間を過ぎるとURLが機能しない可能性がある。

## E. 新チャット最初の具体的作業（この順序）

1. この引継ぎ文書を読む。**次にGitHubとRailwayのコネクタが使えるか実際に試す**。コネクタが見当たらない場合「引継ぎ不可能」と即断せず、接続状況を確認する。利用不可なら制限を正直に報告し、接続・権限を確認する。ユーザーに過去の説明を繰り返させない。
2. GitHubで `arva-nouvelle-paradise-bridge` ブランチの `arva-nouvelle-bridge/bridge.cjs`、mainの `arva_vod/build.py`、`.github/workflows/update_arva_vod.yml` を**現在の内容から読み直す**。
3. Railwayの対象サービスの最新deployment・起動ログ・HTTPログを確認。クエリ文字列（認証キー）を表示せず、ステータスとエラーを確認する。デプロイSUCCESSを再生SUCCESSと誤認しない。
4. 根本原因について**同一デプロイの同一VODクリップが2026-10-19 09:28に200、14:17に502となった事実**から比較。上流仕様・鍵・時間条件、配布WASMの実体、通信条件差を検証可能なものから調べる。復号・アクセス制御が回避できると決めつけない。
5. 再生に関係のない診断コミットを繰り返さず、検証設計→必要な小修正→ログ/テスト→実際の再生確認を明確に分ける。新規機能を入れる場合は**本番チャンネル、VOD、EPGの退行テスト**を優先。
6. Railwayへの自動試行を増やさない。現行の3件連続502停止と429クールダウンを維持する。ライブやVODの復旧確認を**成功したことにしない**。
7. 原因またはコードの実修正ができた場合、コミットSHA、対象ファイル、再デプロイ結果、再生確認の可否を分けて報告する。必要ならこの文書も更新し、次回はここから再開する。

## F. 対話上の重要な注意

- ユーザーはアプリに「この会話は長すぎるため、続けられません。新しいチャットを開始して…」という画面が出て新チャットを強制されている。安易にまた「次チャットへ」と誘導しない。
- 以前、次チャットで「引き継げない」と回答され、ユーザーが不信感を抱いている。**文章だけでなくGitHubに保存したのはその対策**。
- ユーザーは検証操作の繰り返しではなく、**原因究明と実再生の回復**を期待している。
- 成果が不明なら「未解決」と明確に言う。実作業をしていないのに「続けている」「裏で監視している」と言わない。
- 次のチャットでの最初の短い応答は「GitHubに保存された引継ぎを読み、実環境を確認してArvaの原因究明を再開する」でよい。あとは実際にツールで調べること。

**終了時点：Arvaの再生未復旧。VOD保全とnewblogフォールバックの修正は検証済み。次は復号障害の根本原因の比較・特定。**


## G. Arva retirement decision (2026-10-19)

The user later directed removal of Arva from FreeWiFi and migration of VOD entries to another supported format. This decision supersedes the earlier no-removal guard above.

- Remove the Arva Teletama/tvk test rows and the Arva Nouvelle Paradise live row from published FreeWiFi while retaining the approved newblog Nouvelle Paradise row.
- Remove all nine Arva bridge VOD rows. Keep the two programmes already validated for newblog replay (`探偵！ナイトスクープ` via ABC and `土曜のあさはほめるちゃん` via MBS) as explicit newblog replay VOD entries, using the current six-day replay templates and expiring entries outside the supported window.
- Do not substitute unrelated KICK recordings for the seven unavailable Arva broadcasts. Keep the existing KICK catalogue unchanged.
- Disable the Arva VOD scheduled publisher so later runs cannot restore Arva entries. Keep EPG source data and other FreeWiFi/Newblog/KICK workflows intact.
- Arva playback remains unverified; successful repository update or workflow run is not playback success.
