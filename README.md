# SendGrid Text Mailer

SendGrid公式Python SDKを使用して、宛先CSVから個別のプレーンテキストメールを送信するCLIツールです。

## 方針

- `text/plain` メール専用
- 1宛先につき1通送信
- 開封・クリックトラッキングは無効
- 宛先や送信履歴などの実運用データはGit管理しない
- Python環境と依存関係はuvで管理

## Development

```powershell
uv sync
uv run sendgrid-text-mailer
uv run ruff check .
uv run pytest
```
