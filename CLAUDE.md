# job-search-agent 開発ルール

## ブランチ戦略
- `main` : 本番用。動作確認済みのコードのみマージする
- `develop` : 開発用。普段の作業はここをベースにする
- `feature/xxx` : 機能ごとの作業ブランチ。developから分岐し、developにマージする

### 作業フロー
```
git checkout -b feature/機能名    # 作業開始
git add . && git commit -m "説明" # 変更を保存
git checkout develop              # developに戻る
git merge feature/機能名          # developに取り込む
git push origin develop           # GitHubに反映
```

### 本番反映
```
git checkout main
git merge develop
git push origin main
```

## 機密ファイルの管理
以下のファイルはGitにコミットしない（.gitignoreで除外済み）：
- `.env` : APIキー（OpenAI等）
- `credentials.json` : Google OAuth認証情報
- `token.json` : Google認証トークン

## 技術スタック
- **言語**: Python 3.13
- **AIエージェント**: OpenAI API (GPT)
- **ブラウザ自動化**: Playwright (Chromium)
- **Google連携**: Google Sheets API (OAuth2.0)
- **スケジュール実行**: Windowsタスクスケジューラ
- **環境変数管理**: python-dotenv

## Google Sheetsの構成
| シート名 | 用途 |
|---------|------|
| 求人サイト一覧 | A列: サイト名、B列: URL |
| 検索条件 | A列: キーワード |
| 結果 | 自動書き込み（求人情報） |

## 検索条件
- フィルタリング条件: 在宅・リモート・テレワーク
