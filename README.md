# SendGrid Text Mailer

SendGrid で、CSV の宛先ごとにパーソナライズした `text/plain` メールを安全に送信する日本語業務メール向け CLI です。

初回の設定から本番送信までの詳細は、[日本語クイックスタート](docs/quick-start-ja.md)を参照してください。

## できること

- CSV の宛先へ、1 件ずつパーソナライズしたテキストメールを送信
- PDF・PNG・JPEG の通常添付
- `validate`、`preview`、`test`、`send` を分離した送信フロー
- 送信済み宛先の重複送信防止と、SQLite による実行履歴の保存
- SendGrid の送信元検証と配信停止グループを送信前に確認
- 担当者別キャンペーンの一括生成と、成功済みメッセージ ID の CSV 出力

## 対象外

HTML メール、本文内画像、PDF・PNG・JPEG 以外の添付、開封・クリック測定、SendGrid Dynamic Templates、Web 管理画面、配信予約・並列送信、および配信停止フォームそのものは対象外です。

## 安全上の仕様

- 本番送信は `--confirm SEND`、テスト送信は `--confirm TEST` が必須です。
- `test` と `send` は、送信元が SendGrid で検証済みであり、配信停止グループを取得できる場合だけ送信します。確認できない場合は 1 件も送信しません。
- 本番送信の重複判定には `campaign_id + email` を使用します。別の案内には新しい `campaign_id` を使用してください。テスト履歴は `test-<campaign_id>` として本番履歴から分離されます。
- 添付は 1 ファイル 10 MiB、合計 15 MiB までです。実運用の宛先 CSV、添付、キャンペーン、SQLite DB、`.env` は Git にコミットしないでください。

## 必要環境とセットアップ

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- SendGrid API キー
- SendGrid で検証済みの送信元と配信停止グループ

PowerShell でリポジトリのルートから実行します。

```powershell
uv sync
Copy-Item .env.example .env
```

`.env` には共通設定だけを保存します。

```dotenv
SENDGRID_API_KEY=your_sendgrid_api_key
MAILER_DATABASE_PATH=data/sendgrid-text-mailer.sqlite3
```

送信元、Reply-To、配信停止グループは `.env` に置かず、キャンペーンごとの `campaign.toml` に設定します。

## 通常のキャンペーン作成と送信

1. 宛先 CSV を用意します。`email` 列は必須で、UTF-8（BOM の有無は不問）を使用します。空欄・不正形式・重複がある場合は検証で停止します。
2. キャンペーンを作成し、生成された `subject.txt` と `body.txt` を編集します。

```powershell
uv run sendgrid-text-mailer campaign create `
  --campaign-id pc-special-sale-2026-08 `
  --name "PC special sale August 2026" `
  --recipients-file .\data\recipients.csv `
  --from-email sender@example.com `
  --from-name "Example Sender" `
  --reply-to reply@example.com `
  --unsubscribe-group-id 12345 `
  --unsubscribe-url "https://example.com/unsubscribe" `
  --max-send-count 300
```

作成先を変更する場合は `--output .\campaigns\<campaign-id>`、送信間隔を変更する場合は `--send-interval-seconds 1.0` を追加します。

次に、以下の順序で確認してから本番送信します。

```powershell
# ローカルファイルと宛先を検証（SendGrid へ接続しない）
uv run sendgrid-text-mailer validate --campaign .\campaigns\pc-special-sale-2026-08

# 描画結果を確認（送信しない）
uv run sendgrid-text-mailer preview `
  --campaign .\campaigns\pc-special-sale-2026-08 `
  --limit 3

# 自分または確認担当者へテスト送信
uv run sendgrid-text-mailer test `
  --campaign .\campaigns\pc-special-sale-2026-08 `
  --to your-address@example.com `
  --confirm TEST

# 本番送信
uv run sendgrid-text-mailer send `
  --campaign .\campaigns\pc-special-sale-2026-08 `
  --confirm SEND
```

`campaign.toml` では `from_email`、`from_name`、`reply_to_list`、`unsubscribe_group_id` を必須で指定します。`unsubscribe_url` を設定した場合は、本文内の `{unsubscribe_url}` が置換されます。宛名には `{recipient_block}` を使用できます。設定項目と本文の書式は[クイックスタート](docs/quick-start-ja.md)を参照してください。

### 添付ファイル

`campaign.toml` に、キャンペーンディレクトリからの相対パスで指定します。

```toml
attachments = [
  "attachments/guide.pdf",
  "attachments/product.png",
]
```

PDF、PNG、JPEG（`.jpg` / `.jpeg`）のみ指定できます。空・重複・不在のファイル、拡張子と内容が一致しないファイル、上限超過は `validate` で停止します。ファイル名は先頭を英数字とし、以降は英数字・半角スペース・`.`・`_`・`-` のみ使用してください。

## 担当者別キャンペーンの一括作成

通常作成とは別の機能です。宛先 CSV の `sender_id` ごとに、送信元と宛先を分離した複数キャンペーンを生成します。

```powershell
# CSV とテンプレートファイルを個別に指定する方式
uv run sendgrid-text-mailer campaign create-from-template --help

# 共通設定をテンプレートディレクトリで管理する方式
uv run sendgrid-text-mailer campaign create-from-template-dir `
  --template-dir .\data\thanksmail-template `
  --output .\campaigns
```

入力 CSV、署名、テンプレート変数、再生成条件、生成後の確認手順は、[担当者別キャンペーンの一括作成ガイド](docs/batch-campaigns-ja.md)を参照してください。

## 履歴とメッセージ ID の出力

```powershell
# 最近の実行履歴
uv run sendgrid-text-mailer history --limit 20

# キャンペーンの本番・テスト履歴
uv run sendgrid-text-mailer history `
  --campaign-id pc-special-sale-2026-08 `
  --limit 20

# 本番送信の成功済みメッセージ ID を CSV 出力（DB は読み取り専用）
uv run sendgrid-text-mailer history export `
  --campaign-id pc-special-sale-2026-08
```

テスト送信の ID は `--mode test` を追加します。既定では `data/<campaign-id>-ids.csv` に UTF-8 BOM 付きで出力されます。出力 CSV には個人情報を含むため、Git にコミットしないでください。

出力先を変更する場合は `--output .\data\custom-message-ids.csv` を指定します。既存ファイルを上書きする場合だけ `--force` を追加してください。

## 開発

```powershell
uv sync
uv run ruff check .
uv run pytest -q
```

認証情報と個人情報の取り扱いは [SECURITY.md](SECURITY.md)、ライセンスは [MIT License](LICENSE) を参照してください。
