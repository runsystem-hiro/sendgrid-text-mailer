# SendGrid Text Mailer クイックスタート

このガイドでは、環境設定済みの `sendgrid-text-mailer` を使って、宛先CSVの準備から本番送信までを行う手順を説明します。

> すべてのコマンドは、`sendgrid-text-mailer` リポジトリのルートで実行してください。

---

## 1. リポジトリのルートを開く

PowerShellで `sendgrid-text-mailer` フォルダを開きます。

現在の場所を確認します。

```powershell
pwd
```

---

## 2. 宛先CSVを用意する

宛先CSVを `data` フォルダに保存します。

例：

```text
data/recipients-pc-sale-2026-08.csv
```

CSV形式：

```csv
email,last_name,first_name,company
taro.yamada@example.com,山田,太郎,サンプル株式会社
hanako.sato@example.com,佐藤,花子,テスト商事株式会社
contact@example.net,,,見本株式会社
```

入力ルール：

- `email` は必須
- `last_name` は姓
- `first_name` は名
- `company` は会社名
- 姓名には「様」を付けない
- UTF-8形式で保存する

---

## 3. キャンペーンを作成する

メール配信ごとに、固有のキャンペーンIDを指定して作成します。

```powershell
uv run sendgrid-text-mailer campaign create `
  --campaign-id pc-sale-2026-08 `
  --name "PC特別販売 2026年8月" `
  --recipients-file .\data\recipients-pc-sale-2026-08.csv `
  --unsubscribe-url "https://example.com/unsubscribe"
```

実運用では、指定された配信停止フォームURLを使用してください。

作成される構成：

```text
campaigns/
└─ pc-sale-2026-08/
   ├─ campaign.toml
   ├─ subject.txt
   └─ body.txt
```

別の案内を送る場合は、新しいキャンペーンIDを使用します。

---

## 4. 件名を編集する

作成された `subject.txt` を開きます。

```text
campaigns/pc-sale-2026-08/subject.txt
```

例：

```text
【ご案内】法人向けPC特別販売のお知らせ
```

件名は1行で入力します。

---

## 5. 本文を編集する

作成された `body.txt` を開きます。

```text
campaigns/pc-sale-2026-08/body.txt
```

例：

```text
{recipient_block}

平素よりお世話になっております。

本文を入力してください。

▼ 配信停止はこちらから
{unsubscribe_url}
```

次の変数は削除しないでください。

```text
{recipient_block}
{unsubscribe_url}
```

- `{recipient_block}` は会社名と宛名に置き換わります
- `{unsubscribe_url}` は配信停止フォームURLに置き換わります

---

## 6. 内容を検証する

```powershell
uv run sendgrid-text-mailer validate `
  --campaign .\campaigns\pc-sale-2026-08
```

エラーが表示された場合は、送信せずにCSVまたはキャンペーンファイルを修正します。

---

## 7. プレビューを確認する

```powershell
uv run sendgrid-text-mailer preview `
  --campaign .\campaigns\pc-sale-2026-08 `
  --limit 3
```

次を確認します。

- 宛名
- 件名
- 本文
- 改行
- 配信停止URL

この操作ではメールは送信されません。

---

## 8. テスト送信する

自分または確認担当者のメールアドレスへ送信します。

```powershell
uv run sendgrid-text-mailer test `
  --campaign .\campaigns\pc-sale-2026-08 `
  --to your-address@example.com `
  --confirm TEST
```

受信したメールを確認します。

修正が必要な場合は、`subject.txt` または `body.txt` を編集し、検証・プレビュー・テスト送信を再実行します。

---

## 9. 本番送信する

```powershell
uv run sendgrid-text-mailer send `
  --campaign .\campaigns\pc-sale-2026-08 `
  --confirm SEND
```

送信前に表示される次の内容を確認します。

- 送信元
- 配信停止グループID
- 配信停止済み件数
- 送信可能件数
- 除外件数

配信停止リストを取得できない場合は、安全のため送信されません。

---

## 10. 送信履歴を確認する

```powershell
uv run sendgrid-text-mailer history --limit 20
```

キャンペーンID、送信結果、成功件数、失敗件数を確認します。

同じキャンペーンを再実行した場合、送信済みの宛先は重複送信されません。

---

# 基本手順

```powershell
# 1. 宛先CSVを data フォルダへ保存

# 2. キャンペーン作成
uv run sendgrid-text-mailer campaign create `
  --campaign-id <キャンペーンID> `
  --name "<キャンペーン名>" `
  --recipients-file .\data\<宛先CSV> `
  --unsubscribe-url "<配信停止URL>"

# 3. subject.txt と body.txt を編集

# 4. 検証
uv run sendgrid-text-mailer validate `
  --campaign .\campaigns\<キャンペーンID>

# 5. プレビュー
uv run sendgrid-text-mailer preview `
  --campaign .\campaigns\<キャンペーンID> `
  --limit 3

# 6. テスト送信
uv run sendgrid-text-mailer test `
  --campaign .\campaigns\<キャンペーンID> `
  --to <確認用メールアドレス> `
  --confirm TEST

# 7. 本番送信
uv run sendgrid-text-mailer send `
  --campaign .\campaigns\<キャンペーンID> `
  --confirm SEND

# 8. 履歴確認
uv run sendgrid-text-mailer history --limit 20
```

## Git管理について

次の実運用データはGit管理外です。

```text
data/*
campaigns/*
```

ただし、公開サンプルとして次のファイルはGit管理されます。

```text
data/.gitkeep
campaigns/example/
```
