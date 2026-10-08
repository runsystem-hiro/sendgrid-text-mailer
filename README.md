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
- SendGrid ASMをメールに設定せず、任意の外部配信停止フォームURLを本文へ掲載
- `campaign_id + email` による重複送信防止
- `validate`、`preview`、`test`、`send` を分離
- 本番送信は `--confirm SEND`、テスト送信は `--confirm TEST` が必須
- SQLiteによる実行履歴と送信結果の保存
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
SENDGRID_FROM_EMAIL=sender@example.com
SENDGRID_FROM_NAME=Example Sender
SENDGRID_REPLY_TO_LIST=first-reply@example.com,second-reply@example.com
SENDGRID_UNSUBSCRIBE_GROUP_ID=12345
MAILER_DATABASE_PATH=data/sendgrid-text-mailer.sqlite3
```

`SENDGRID_REPLY_TO_LIST` は、受信者が通常の「返信」をした際の宛先です。複数指定する場合は
カンマ区切りで指定します。設定すると、すべてのアドレスへ返信が届きます。未設定の場合は、
返信先は `SENDGRID_FROM_EMAIL` になります。本番送信前の確認表示に Reply-To の設定値を表示します。

`.env`、実在する宛先CSV、実運用キャンペーン、SQLiteデータベースは
Gitへコミットしないでください。

## キャンペーンの作成

雛形はCLIから作成できます。

```powershell
uv run sendgrid-text-mailer campaign create `
  --campaign-id pc-special-sale-2026-08 `
  --name "PC special sale August 2026" `
  --recipients-file .\data\recipients.csv `
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
  --unsubscribe-url "https://example.com/unsubscribe" `
  --output .\campaigns\sample-1
```

### campaign.toml

```toml
campaign_id = "pc-special-sale-2026-08"
name = "PC special sale August 2026"
recipients_file = "../../data/recipients.csv"
max_send_count = 300
send_interval_seconds = 1.0
unsubscribe_url = "https://example.com/unsubscribe?group_id=12345"

# Optional: PDF, PNG, or JPEG files only, relative to this campaign directory.
attachments = [
  "attachments/guide.pdf",
  "attachments/product.png",
]
```

`campaign_id` は送信済み判定に使用します。同じ配信の途中で変更せず、
別の案内では新しいIDを使用してください。

`unsubscribe_url` には、受信者が配信停止を申請できる外部フォームの完成済み絶対 URL を指定します。
本文に `{unsubscribe_url}` を記載すると、その URL に置き換わります。SendGrid ASM は送信メールに設定しません。

### 添付ファイル

`attachments` は省略可能です。指定する場合はキャンペーンディレクトリからの相対パスで、PDF、PNG、JPEG（`.jpg` / `.jpeg`）のみを配列で指定します。複数ファイルを指定できます。ZIPを含むその他の形式は拒否します。

- 1ファイル上限: 10 MiB
- 添付合計上限: 15 MiB
- 空ファイル、重複、存在しないファイル、拡張子とファイルヘッダーが一致しないファイルは `validate` の時点で拒否
- ファイル名は、先頭を英数字とし、以降は英数字・半角スペース・`.`・`_`・`-` のみ使用可能（日本語・全角文字・その他の記号は `validate` で拒否し、ASCII名への変更例を表示）
- 添付内容はログへ出力しません
- 画像は通常添付のみです。本文内表示・インライン画像には対応しません

実運用の添付ファイルはGitへコミットしないでください。`campaigns/*/attachments/` は既存のローカルキャンペーン除外ルールにより追跡対象外です。`preview`、`test`、`send` では添付予定のファイル名とサイズを表示します。テスト送信にも本番と同じ添付ファイルを付けます。

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

# 3. 自分宛てにテスト送信（件名へ [TEST] を自動付与）
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
```

本番送信前には、送信元、配信停止グループID、配信停止リスト件数、
送信可能件数、除外件数を表示します。

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
