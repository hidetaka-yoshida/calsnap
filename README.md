# かるスナップ (CalSnap)｜低コスト・スマホ対応カロリー管理アプリ

スマホからの直接カメラ撮影〜画像ロードに対応し、毎日のカロリー・栄養価（PFC）を概算・記録して基礎代謝量（BMR）から良否判定と日・週・月の可視化を行うWebアプリです。

## 特長
- **スマホ最適化＆直接カメラ撮影**: 「📷 カメラで撮影する」からOS標準カメラを直接起動し、自動で軽量リサイズ（最大512px JPEG）して概算・記録できます。
- **完全無料〜超低コスト設計**:
  - デフォルトは内蔵日本食辞書＋画像色味ローカル推定で **APIコスト0円**。
  - 任意で Gemini Flash-Lite API を設定画面から有効化可能。
- **ローカル（SQLite）とGCP（Cloud Run + Firestore + Cloud Storage）の両対応**:
  - 開発・テスト時はローカルSQLite、本番はサーバーレスなGCP無料枠構成に切り替えられます。
- **Googleアカウント認証＆家族共有対応**: `GOOGLE_CLIENT_ID` と `ALLOWED_EMAILS` を設定することで、家族それぞれが自分のデータ空間を利用できます。

---

## 1. ローカルでの起動方法（SQLiteモード）

```bash
cd /Users/hidetakayoshida/Documents/PJ_Diet
python3 server.py
```

ブラウザで `http://127.0.0.1:8080` を開きます（`APP_PASSCODE=1234 python3 server.py` で簡易パスコード保護の動作確認も可能）。

---

## 2. GCP（Cloud Run + Firestore + Cloud Storage）へのデプロイ手順

Cloud SQL のような時間課金インスタンスを使わず、**Cloud Run（最小インスタンス0）＋ Firestore（Nativeモード）＋ Cloud Storage** を使うことで、個人・家族利用では無料枠内（〜月数円）で運用できます。

### 事前準備（初回のみ）
1. GCPプロジェクトを作成（例: `pjt-calsnap` または全世界一意な `pjt-calsnap-001` 等）し、**Cloud Run**, **Cloud Build**, **Firestore**, **Cloud Storage** APIを有効化
2. **Firestore** を **Nativeモード** で作成（無料枠を使う場合は `(default)` データベース）
3. **Cloud Storage** バケットを作成（例: `calsnap-images-<project-id>`、非公開設定のままでOK）

### デプロイコマンド（家族でGoogleログインを使う場合）

1. GCPコンソールの **Google Auth Platform（OAuth同意画面）→ クライアント** で「ウェブアプリケーション」の **OAuth 2.0 クライアントID** を作成し、「承認済みの JavaScript 生成元」に Cloud Run のURL（例: `https://calsnap-xxxx.a.run.app`）を登録します。
2. 以下の環境変数を指定してデプロイします（`ALLOWED_EMAILS` を指定すると家族のメールアドレスのみログイン許可できます）：

```bash
cd /Users/hidetakayoshida/Documents/PJ_Diet

gcloud run deploy calsnap \
  --source . \
  --region asia-northeast1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 2 \
  --memory 256Mi \
  --set-env-vars "STORAGE_BACKEND=gcp,GCS_BUCKET=calsnap-images-<project-id>,GOOGLE_CLIENT_ID=<クライアントID>,ALLOWED_EMAILS=family1@gmail.com,family2@gmail.com"
```

> ※ `GOOGLE_CLIENT_ID` の代わりに `APP_PASSCODE=1234` を使うと、個人用の簡易パスコードロックモードになります。
> ※ Cloud Run の実行サービスアカウントに「Cloud Datastore ユーザー（Firestore読み書き）」と「ストレージ オブジェクト管理者（GCSバケット読み書き）」の権限が付与されていることを確認してください。

デプロイ後に発行される `https://calsnap-xxxx.a.run.app` をスマホのSafari / Chromeで開き、「ホーム画面に追加」するとアプリのように使えます。

---

## テスト実行

```bash
python3 -m unittest discover -s tests -v
```
