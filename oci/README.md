# Oracle Cloud Always Free 移行準備（並行稼働テスト）

目的: `ajiousama/himitsu` の現行 Railway 2 サービス (`freewifi-radio` と `patapata-r14`) を、既存 URL と配信を壊さずに Oracle 側で検証する。

## Oracle の作成前チェック
- OCI Console へのログインは所有者本人が実施する。このリポジトリには OCI 認証情報、SSH 秘密鍵、Radiko ログイン情報を保存しない。
- テナンシの **ホームリージョン** で、**Always Free 対象** `VM.Standard.A1.Flex` を選ぶ。契約画面上の無料トライアル利用可能残高だけを根拠に「永久無料」と判断しない。
- 無料継続を前提とする現行 Oracle 文書の目安: A1 合計 **2 OCPU / 12 GB RAM**、ブートを含むブロックボリューム **合計 200 GB** 以内。別の用途のVM/ディスクも合算する。
- Ubuntu 24.04 arm64 など、選択シェイプと互換性のある Linux イメージを選ぶ。サーバー作成後、Docker Engine / Compose plugin のインストールと GitHub からの正規のリポジトリ取得が必要。
- OCI 側のインターネット公開・ファイアウォール設定・HTTPS ドメインは別途準備する。最初から管理ポートを無制限公開しない。

## 初期検証（既存の公開 URL は変更しない）

リポジトリを OCI サーバーに正規のアクセス権でチェックアウト後、Linux 上で:
```bash
bash oci/start.sh
bash oci/check.sh
```

`oci/compose.yml` が **既存の Railway Dockerfile** を再利用して、同一サーバー上で2サービスを別コンテナで起動する。検証用ポートは `127.0.0.1:18080`（radio）と `127.0.0.1:18081`（patapata）のみで、外部には開いていない。

確認順:
1. A1 / 無料範囲 / ホームリージョン / ボリューム容量を最終確認。
2. コンテナのビルド、`/health`、ログ、起動再試行を確認。
3. ラジオ MPEG-TS とパタパタ HLS を長時間再生して負荷と安定性を確認（2 OCPU で 1080p 配信が成立するかは未検証）。
4. HTTPS 経由の公開・プレイヤー検証後、元 URL を保持するプロキシ経由で段階的に切替える。
5. 切替完了・安定性確認後にのみ Railway 側の停止を検討。

**本ブランチは準備用。OCI VM の作成・配信切替・Railway停止は未実施。** Render / Vercel / KICK / HARU / TVer を一括して移すこともしていない。
