# 担当者別キャンペーンの一括作成

展示会後のお礼メールなどで、担当者ごとに送信元と宛先を分ける場合の手順です。通常の `campaign create` は 1 件のキャンペーンを作るため、この機能とは使い分けます。

すべてのコマンドは、PowerShell でリポジトリのルートから実行してください。

## 共通の入力ルール

- 宛先 CSV は UTF-8 で、`email` と `sender_id` 列が必要です。
- 送信者 CSV は UTF-8 で、`from_name` と `from_email` 列が必要です。
- 宛先 CSV の `sender_id` は、送信者 CSV の `from_name` と完全一致させます。
- 空の担当者、未登録担当者、重複した `from_name`、無効な送信元メールアドレスがある場合は生成前に停止します。
- 担当者ごとのキャンペーン ID は、送信元メールアドレスの `@` より前を元に作成されます。
- 出力先またはマニフェストが既に存在する場合は上書きせず停止します。

最小の宛先 CSV（`all.csv`）です。

```csv
email,sender_id,company
customer-one@example.com,営業担当者A,サンプル株式会社
customer-two@example.com,営業担当者B,テスト商事株式会社
```

最小の送信者 CSV（`sender-list.csv`）です。

```csv
from_name,from_email
営業担当者A,sender-a@example.com
営業担当者B,sender-b@example.com
```

送信者 CSV には、部署・役職・電話番号など任意の列を追加できます。これらは件名・本文で `{department}` のように参照できます。共通して使える `{from_name}`、`{from_email}`、`{sender_id}` と、宛先 CSV の各列も同様に使用できます。

## 方法 1: CSV とテンプレートファイルを個別指定する

件名・本文・CSV のファイルを明示して生成する方式です。

```powershell
uv run sendgrid-text-mailer campaign create-from-template `
  --campaign-id-prefix japan-it-week-2026-autumn-thanks `
  --name-prefix "Japan IT Week 2026 秋 ご来場御礼" `
  --recipients-file .\data\all.csv `
  --sender-list-file .\data\sender-list.csv `
  --subject-template-file .\data\subject.txt `
  --body-template-file .\data\body.txt `
  --unsubscribe-group-id 42437 `
  --max-send-count 177 `
  --output .\campaigns
```

必要に応じて、以下を追加します。

- `--reply-to reply@example.com`：Reply-To を指定します。複数指定できます。
- `--unsubscribe-url "https://example.com/unsubscribe"`：外部配信停止フォーム URL を指定します。
- `--send-interval-seconds 1.0`：送信間隔を変更します。
- `--sender-id-column 担当者`：宛先 CSV の担当者列名を変更します。
- `--from-name-column 送信者名`：送信者 CSV の氏名列名を変更します。

本文で `{signature}` を使う場合は、`--signature-template-file .\data\signature.txt` が必要です。生成された各 `signature.txt` は必要に応じて担当者別の内容へ編集してください。

## 方法 2: テンプレートディレクトリを指定する

共通設定と入力ファイルを一つのディレクトリで管理する方式です。担当者別の署名マスターも管理したい場合はこちらを使用します。

```text
data/thanksmail-template/
├── campaign.toml
├── all.csv
├── sender-list.csv
├── subject.txt
├── body.txt
└── signatures/
    ├── sender-a.txt
    └── sender-b.txt
```

`campaign.toml` の必須項目は `campaign_id_prefix`、`name`、`unsubscribe_group_id`、`max_send_count` です。`reply_to_list`、`unsubscribe_url`、`send_interval_seconds` は必要に応じて指定します。

```toml
campaign_id_prefix = "japan-it-week-2026-autumn-thanks"
name = "Japan IT Week 2026 秋 ご来場御礼"
reply_to_list = []
unsubscribe_group_id = 42437
max_send_count = 177
send_interval_seconds = 1.0
```

この方式の `sender-list.csv` には `signature_file` 列も必要です。値はテンプレートディレクトリからの相対パスで指定し、ディレクトリ外のファイルは指定できません。

```csv
from_name,from_email,signature_file,department
営業担当者A,sender-a@example.com,signatures/sender-a.txt,営業部
営業担当者B,sender-b@example.com,signatures/sender-b.txt,営業部
```

生成コマンドです。

```powershell
uv run sendgrid-text-mailer campaign create-from-template-dir `
  --template-dir .\data\thanksmail-template `
  --output .\campaigns
```

この方式で生成したキャンペーンは、テンプレート側の `campaign.toml`、CSV、件名、本文、`signatures/` 配下の署名マスターの変更を検出します。いずれかを変更した場合、既存キャンペーンの `validate`、`preview`、`test`、`send` は停止します。既存の生成物を編集して続行せず、再生成してください。

## 生成後の確認と送信

生成時に `<campaign-id-prefix>-manifest.csv` が出力されます。キャンペーン ID、送信元、宛先数、署名の状態を確認してください。宛先メールアドレスと本文は出力されません。

各キャンペーンで、必ず次の順序で確認します。

```powershell
uv run sendgrid-text-mailer validate --campaign .\campaigns\<campaign-id>
uv run sendgrid-text-mailer preview --campaign .\campaigns\<campaign-id> --limit 3
uv run sendgrid-text-mailer test `
  --campaign .\campaigns\<campaign-id> `
  --to your-address@example.com `
  --confirm TEST
```

すべての確認が完了したキャンペーンだけ、本番送信してください。

```powershell
uv run sendgrid-text-mailer send `
  --campaign .\campaigns\<campaign-id> `
  --confirm SEND
```
