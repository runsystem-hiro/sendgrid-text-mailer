# SendGrid Text Mailer

SendGrid公式Python SDKを使用して、CSVの宛先へ1件ずつパーソナライズした
`text/plain` メールを安全に送信するCLIツールです。

## 主な安全設計

- HTML・画像・添付ファイルには対応しない
- 開封トラッキングとクリックトラッキングをメール単位で無効化
- SendGridの配信停止グループを送信前に取得
- SendGrid ASMはメールへ設定せず、外部配信停止フォームのURLを本文に掲載
- 配信停止リストを取得できない場合は送信を中止
- `campaign_id + email` で送信済みを判定し、重複送信を防止
- 実送信は `--confirm SEND`、テスト送信は `--confirm TEST` が必須
- キャンペーンごとの最大送信件数を設定
- 実行結果をSQLiteへ保存

## セットアップ

```powershell
uv sync
Copy-Item .env.example .env
```

`.env` にSendGrid APIキー、認証済み送信元、配信停止グループIDを設定します。
`.env`、宛先データ、実運用キャンペーン、SQLiteデータベースはGit管理しません。

## キャンペーン

```text
campaigns/<campaign-name>/
├── campaign.toml
├── subject.txt
└── body.txt
```

`campaign.toml` の例：

```toml
campaign_id = "pc-special-sale-2026-08"
name = "PC special sale August 2026"
recipients_file = "../../data/recipients.csv"
max_send_count = 300
send_interval_seconds = 1.0
unsubscribe_url = "https://example.com/unsubscribe?group_id=12345"
```

`campaign_id` は送信済み判定に使用するため、同じ配信の途中で変更しないでください。
別の案内を送る場合は新しい `campaign_id` を使用します。

`unsubscribe_url` には、受信者が配信停止を申請できる外部フォームの完成済みURLを指定します。
SendGrid ASMをメールへ設定しないため、SendGrid独自の配信停止リンクは自動挿入されません。
一方、送信前の配信停止グループ確認には `.env` の
`SENDGRID_UNSUBSCRIBE_GROUP_ID` を引き続き使用します。

## 宛先CSV

```csv
email,last_name,first_name,company
taro.yamada@example.com,山田,太郎,サンプル株式会社
```

- `email` 列は必須
- UTF-8（BOMあり・なし）に対応
- メールアドレスは前後空白を除去し、小文字で比較
- 重複、不正形式、空欄が1件でもあれば送信前に中止
- その他の列はテンプレート変数として使用可能
- `{full_name}` は自動生成（例：`山田 太郎 様`）
- `{unsubscribe_url}` は `campaign.toml` の設定値を使用

## コマンド

```powershell
# ファイルと宛先を検証（SendGridへ接続しない）
uv run sendgrid-text-mailer validate --campaign campaigns/example

# 先頭3件をプレビュー
uv run sendgrid-text-mailer preview --campaign campaigns/example --limit 3

# 指定した1アドレスへテスト送信
uv run sendgrid-text-mailer test `
  --campaign campaigns/example `
  --to your-address@example.com `
  --confirm TEST

# 本番送信
uv run sendgrid-text-mailer send `
  --campaign campaigns/example `
  --confirm SEND

# 最近の実行履歴
uv run sendgrid-text-mailer history --limit 20
```

## 開発確認

```powershell
uv run ruff check .
uv run pytest
```
