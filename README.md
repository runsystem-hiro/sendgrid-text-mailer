# SendGrid Text Mailer

SendGrid公式Python SDKを使用し、CSVの宛先へパーソナライズした
`text/plain` メールを1件ずつ安全に送信する、日本語業務メール向けCLIです。

## クイックスタート

初めて利用する場合は、[日本語クイックスタート](docs/quick-start-ja.md)を参照してください。

## 特徴

- HTMLや本文内画像を扱わないシンプルなテキストメール専用設計
- PDF、PNG、JPEGファイルの通常添付に対応
- 開封・クリックトラッキングをメール単位で無効化
- SendGridの配信停止グループを送信前に確認し、取得失敗時は送信を中止
- 指定した送信元がSendGridで検証済みであることを送信前に確認
- SendGrid ASMをメールに設定せず、任意の外部配信停止フォームURLを本文へ掲載
- `campaign_id + email` による重複送信防止
- `validate`、`preview`、`test`、`send` を分離
- 本番送信は `--confirm SEND`、テスト送信は `--confirm TEST` が必須
- SQLiteによる実行履歴と送信結果の保存
- 送信中の進捗・失敗・推定残り時間の表示
- `uv` による環境・依存関係管理

## 対象外

次の用途には対応しません。

- HTMLメール
- 本文内画像、インライン画像
- ZIPを含む、PDF・PNG・JPEG以外の添付ファイル
- 開封率・クリック率の測定
- SendGrid Dynamic Templates
- Web管理画面、配信予約、並列送信
- 配信停止フォーム自体の提供

## 必要環境

- Python 3.13
- uv
- SendGrid APIキー
- SendGridで認証済みの送信元
- SendGridの配信停止グループ

## セットアップ

```powershell
uv sync
Copy-Item .env.example .env
```

`.env` を編集します。

```dotenv
SENDGRID_API_KEY=your_sendgrid_api_key
MAILER_DATABASE_PATH=data/sendgrid-text-mailer.sqlite3
```

送信元・返信先・配信停止グループは、誤ったキャンペーン設定で送信しないよう、`.env` ではなく
各 `campaign.toml` に必須で指定します。

`.env`、実在する宛先CSV、実運用キャンペーン、SQLiteデータベースは
Gitへコミットしないでください。

## キャンペーンの作成

雛形はCLIから作成できます。

```powershell
uv run sendgrid-text-mailer campaign create `
  --campaign-id pc-special-sale-2026-08 `
  --name "PC special sale August 2026" `
  --recipients-file .\data\recipients.csv `
  --from-email sender@example.com `
  --from-name "Example Sender" `
  --reply-to reply@example.com `
  --unsubscribe-group-id 12345 `
  --unsubscribe-url "https://example.com/unsubscribe?group_id=12345" `
  --max-send-count 300 `
  --send-interval-seconds 1.0
```

既定では `campaigns/<campaign-id>/` に次のファイルを作成します。
既存ディレクトリは上書きしません。

```text
campaigns/<campaign-id>/
├── campaign.toml
├── subject.txt
├── body.txt
└── attachments/
    └── guide.pdf
```

作成先を変える場合は `--output` を指定します。

```powershell
uv run sendgrid-text-mailer campaign create `
  --campaign-id sample-1 `
  --name "Sample campaign" `
  --recipients-file .\data\recipients.csv `
  --from-email sender@example.com `
  --from-name "Example Sender" `
  --reply-to reply@example.com `
  --unsubscribe-group-id 12345 `
  --unsubscribe-url "https://example.com/unsubscribe" `
  --output .\campaigns\sample-1
```

### 担当者別キャンペーンの一括作成

展示会後のお礼メールなど、宛先CSVの担当者列ごとに送信元を分ける場合は、
`campaign create-from-template` を使用します。送信は実行せず、担当者ごとに独立した
キャンペーンを作成します。宛先CSVには `email` と `sender_id`、送信者CSVには
`from_name` と `from_email` が必要です。`sender_id` と `from_name` は完全一致する必要があり、
未登録担当者・空の担当者・重複した送信者名は生成前にエラーになります。

`sender-list.csv` の必須列は `from_name` と `from_email` だけです。部署・役職・電話番号など、
担当者ごとに変えたい署名要素は任意の列として追加できます。

```csv
from_name,from_email,sender_last_name,signature_file,department,phone
営業担当者名,verified-sender@example.com,営業担当者の姓,signatures/sender-account.txt,営業部,00-0000-0000
```

件名・本文テンプレートでは、通常の宛先変数に加えて `{from_name}`、`{from_email}`、
`{sender_id}` と、送信者CSVの任意列を使用できます。本文で `{signature}` を使用する場合は
`--signature-template-file` を指定してください。署名テンプレートは固定見本として扱い、
営業担当者が生成後の `signature.txt` を書き換えます。

テンプレートディレクトリから生成する場合、`signature_file` は必須です。テンプレートディレクトリ
からの相対パスで、担当者別マスター署名を指定してください。署名マスターは
`signatures/` 配下に置き、複数行の署名をCSVへ記載しないでください。テンプレート直下の
共通 `signature.txt` は使用しません。

テンプレートディレクトリの `campaign.toml` に、全担当者で共通となる設定を置けます。

```toml
campaign_id_prefix = "japan-it-week-2026-autumn-thanks"
name = "Japan IT Week 2026 秋 ご来場御礼"
reply_to_list = []
unsubscribe_group_id = 42437
max_send_count = 177
send_interval_seconds = 1.0
```

`campaign_id_prefix`、`name`、`unsubscribe_group_id`、`max_send_count` は必須です。
`unsubscribe_url` と `reply_to_list` は必要な場合のみ追加します。担当者別の `from_name`、
`from_email`、`sender_last_name` は引き続き `sender-list.csv` で管理します。

テンプレートディレクトリから作成する場合は、以下を実行します。

```powershell
uv run sendgrid-text-mailer campaign create-from-template-dir `
  --template-dir .\data\thanksmail-template `
  --output .\campaigns
```

生成先が1件でも既に存在する場合は、上書きせずに中止します。生成後は、各ディレクトリで
`signature.txt` を営業担当者本人の署名デザインへ編集できます。`body.txt` の `{signature}` は
送信時に同ファイルの内容へ置き換わります。生成直後の `signature.txt` は固定見本のため、
編集されていない場合、または `campaign.toml` の `from_name` が署名内にない場合は `validate` が
エラーで停止します。編集後は必ず `validate`、`preview`、`test` を実施してから送信してください。

生成時には `<campaign-id-prefix>-manifest.csv` も出力されます。担当者ごとのキャンペーンID、
送信元、宛先件数、署名の対応状況（初期状態は `requires_replacement`）を確認し、署名回収の
管理表として使用してください。宛先メールアドレスおよび本文は出力しません。

担当者ごとのディレクトリ名と `campaign_id` は、送信元メールアドレスの `@` より前だけを
使用します。`campaign.toml` の `name` は全担当者共通で、担当者名は含めません。

テンプレートディレクトリから生成したキャンペーンは、テンプレート側の `campaign.toml`、
`all.csv`、`sender-list.csv`、件名、本文、および `signatures/` 配下の署名マスターをハッシュで
記録します。これらを変更した後は、既存キャンペーンの `validate`・`preview`・`test`・`send` が
停止します。必ず再生成してください。

### campaign.toml

```toml
campaign_id = "pc-special-sale-2026-08"
name = "PC special sale August 2026"
recipients_file = "../../data/recipients.csv"
from_email = "sender@example.com"
from_name = "Example Sender"
reply_to_list = ["reply@example.com"]
unsubscribe_group_id = 12345
max_send_count = 300
send_interval_seconds = 1.0
unsubscribe_url = "https://example.com/unsubscribe?group_id=12345"

# Optional: PDF, PNG, or JPEG files only, relative to this campaign directory.
attachments = [
  "attachments/guide.pdf",
  "attachments/product.png",
]
```

`campaign_id` は本番送信の送信済み判定に使用します。同じ配信の途中で変更せず、
別の案内では新しいIDを使用してください。`test --confirm TEST` は、この値を変更せず、
DB内では `test-<campaign_id>` としてテスト履歴を分離します。

`from_email`、`from_name`、`reply_to_list`、`unsubscribe_group_id` は必須です。`reply_to_list = []`
とすると Reply-To を指定せず、受信者の通常返信は From アドレスへ届きます。これら4項目の
`.env` によるフォールバックは行いません。`test` と `send` は、指定した `from_email` が
SendGrid の Sender Verification で検証済みであることをAPIで確認できなければ送信を中止します。

`unsubscribe_url` には、受信者が配信停止を申請できる外部フォームの完成済み絶対 URL を指定します。
本文に `{unsubscribe_url}` を記載すると、その URL に置き換わります。SendGrid ASM は送信メールに設定しません。
外部フォームを使わない場合は `unsubscribe_url` を省略し、本文で返信による配信停止方法を案内できます。

### 添付ファイル

`attachments` は省略可能です。指定する場合はキャンペーンディレクトリからの相対パスで、PDF、PNG、JPEG（`.jpg` / `.jpeg`）のみを配列で指定します。複数ファイルを指定できます。ZIPを含むその他の形式は拒否します。

- 1ファイル上限: 10 MiB
- 添付合計上限: 15 MiB
- 空ファイル、重複、存在しないファイル、拡張子とファイルヘッダーが一致しないファイルは `validate` の時点で拒否
- ファイル名は、先頭を英数字とし、以降は英数字・半角スペース・`.`・`_`・`-` のみ使用可能（日本語・全角文字・その他の記号は `validate` で拒否し、ASCII名への変更例を表示）
- 添付内容はログへ出力しません
- 画像は通常添付のみです。本文内表示・インライン画像には対応しません

実運用の添付ファイルはGitへコミットしないでください。`campaigns/*/attachments/` は既存のローカルキャンペーン除外ルールにより追跡対象外です。`preview` と `send` では添付予定のファイル名とサイズを表示します。テスト送信にも本番と同じ添付ファイルを付けます。

## 宛先CSV

```csv
email,last_name,first_name,company
taro.yamada@example.com,山田,太郎,サンプル株式会社
contact@example.net,,,テスト商事株式会社
```

- `email` 列は必須
- UTF-8（BOMあり・なし）に対応
- メールアドレスの前後空白を除去し、小文字で比較
- 重複、不正形式、空欄が1件でもあれば送信前に中止
- その他の列はテンプレート変数として利用可能

CSVは `data/` に置くほか、キャンペーンディレクトリ内へ配置できます。`recipients_file` は
`campaign.toml` からの相対パスで指定します。

```toml
# data/ に置く場合
recipients_file = "../../data/recipients.csv"

# campaign.toml と同じディレクトリに置く場合
recipients_file = "recipients.csv"
```

### 日本語宛名

`{full_name}` と `{recipient_block}` を利用できます。

| 会社名 | 姓名 | `{recipient_block}`        |
| ------ | ---- | -------------------------- |
| あり   | あり | 会社名＋改行＋`姓 名 様`   |
| あり   | なし | 会社名＋改行＋`ご担当者様` |
| なし   | あり | `姓 名 様`                 |
| なし   | なし | `ご担当者様`               |

姓だけ、または名だけの場合も、存在する値へ `様` を付けます。
CSVの姓名欄には敬称を含めないでください。

本文例：

```text
{recipient_block}

平素よりお世話になっております。

本文を入力してください。

▼ 配信停止はこちらから
{unsubscribe_url}
```

## 実行手順

```powershell
# 1. ファイルと宛先を検証（SendGridへ接続しない）
uv run sendgrid-text-mailer validate --campaign .\campaigns\example

# 2. 先頭3件をプレビュー
uv run sendgrid-text-mailer preview `
  --campaign .\campaigns\example `
  --limit 3

# 3. 自分宛てにテスト送信（件名へ [TEST] を自動付与。DBでは test-<campaign_id> として記録）
uv run sendgrid-text-mailer test `
  --campaign .\campaigns\example `
  --to your-address@example.com `
  --confirm TEST

# 4. 本番送信
uv run sendgrid-text-mailer send `
  --campaign .\campaigns\example `
  --confirm SEND

# 5. 最近の実行履歴
uv run sendgrid-text-mailer history --limit 20

# 6. 指定したキャンペーンの実行履歴（本番・テストの両方）
uv run sendgrid-text-mailer history `
  --campaign-id example `
  --limit 20

```

`test` と `send` は、メール送信前に指定した送信元の Sender Verification と配信停止リストを確認します。どちらかを確認できない場合は、メールを1件も送信せずに停止します。テスト・本番送信前には送信元、返信先、配信停止グループIDを表示します。本番送信前には加えて、配信停止リスト件数、送信可能件数、除外件数を表示します。

送信中は、対話型端末では1件ごとに同じ行を更新し、10件ごとに確定行を残します。失敗時は直ちに件数を表示しますが、宛先メールアドレスや本文は表示しません。出力をファイルへリダイレクトした場合は、10件ごとの確定行、失敗時、および完了時のみ出力します。推定残り時間は、設定した送信間隔と実測したAPI応答時間から算出します。

`Ctrl+C` で中断した場合は、送信済み・失敗・未試行の件数を表示し、実行履歴には `interrupted` と記録します。強制終了などで終了処理が実行できなかった履歴は `running` のまま残り、完了扱いにはなりません。

`history --campaign-id` には `campaign.toml` の本来の `campaign_id` を指定します。本番履歴に加え、同じキャンペーンの `test-<campaign_id>` として記録されたテスト履歴も表示します。

## キャンペーン別のSendGridメッセージIDをCSV出力

指定した `campaign_id` に一致する成功済み配信（`status = 'sent'` かつ
`message_id` あり）を、1配信1行でCSVへ出力します。DBは読み取り専用で開くため、
配信履歴を変更しません。PowerShellで、リポジトリのルートから実行してください。

```powershell
# 本番送信のメッセージIDを出力
uv run sendgrid-text-mailer history export `
  --campaign-id 2026-10Special-Sale

# テスト送信のメッセージIDを出力
uv run sendgrid-text-mailer history export `
  --campaign-id 2026-10Special-Sale `
  --mode test
```

`--campaign-id` には常に `campaign.toml` の本来のIDを指定します。テスト時の内部IDである
`test-<campaign_id>` を手入力する必要はありません。既定の出力先は次のとおりです。

```text
本番:     data/<campaign-id>-ids.csv
テスト:   data/test-<campaign-id>-ids.csv
```

CSVはUTF-8 BOM付きで保存します。同一宛先へ再送した履歴がある場合は、メッセージIDごとに
複数行出力されます。出力先を変更する場合は `--output` を指定してください。既存のCSVは
上書きせずエラーにするため、意図して上書きする場合だけ `--force` を追加します。

```powershell
uv run sendgrid-text-mailer history export `
  --campaign-id 2026-10Special-Sale `
  --output .\data\custom-message-ids.csv `
  --force
```

```csv
campaign_id,recipient_email,message_id
2026-10Special-Sale,customer-one@example.com,example-message-id-001
2026-10Special-Sale,customer-two@example.com,example-message-id-002
2026-10Special-Sale,customer-three@example.com,example-message-id-003
```

`MAILER_DATABASE_PATH` で既定以外のDBを使用している場合も、同じCLIコマンドでそのDBを
参照します。出力CSVには個人情報を含むため、Gitへコミットしないでください。

## 配信停止の考え方

1. 本文の外部フォーム URL で申請を受け付ける
2. 運用者が対象アドレスをSendGridの配信停止グループへ登録する
3. 次回送信時に本ツールがグループをAPIで確認して除外する

配信停止リストを取得できない場合は、空リストとして続行せず送信を中止します。
外部フォームの実装・本人確認・グループ登録作業は、このリポジトリの対象外です。

## 開発

```powershell
uv sync
uv run ruff check .
uv run pytest -q
```

GitHub ActionsでもRuffとpytestを実行します。

## セキュリティ

認証情報や個人情報の取り扱いは [SECURITY.md](SECURITY.md) を参照してください。

## ライセンス

[MIT License](LICENSE)
