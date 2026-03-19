# 錬語術 — Prompt Alchemy

Word2Vec を使って単語の「近い・遠い」を探索し、Claude API で画像生成プロンプトを生成するツール。

## 構成

```
prompt-alchemy/
├── server.py        # FastAPI サーバー（Word2Vec + Claude API）
├── index.html       # UI
├── style.css        # スタイル
├── app.js           # フロントエンドロジック
├── requirements.txt # Pythonライブラリ一覧
├── .env             # APIキー（Git管理外）
└── README.md
```

モデルファイル（`*.kv`, `*.kv.vectors.npy`）はサイズが大きいため Git 管理外です。別途ダウンロードしてください。

## セットアップ

```bash
# 仮想環境を作成・有効化
python3 -m venv venv
source venv/bin/activate

# ライブラリをインストール
pip install -r requirements.txt
```

## モデルのダウンロード

[chiVe](https://github.com/WorksApplications/chiVe) から `chive-1.2-mc90.kv` と `chive-1.2-mc90.kv.vectors.npy` をダウンロードして、プロジェクトのルートに置く。

## APIキーの設定

`.env` ファイルをプロジェクトのルートに作成する：

```
ANTHROPIC_API_KEY=sk-ant-...
```

`.env` は `.gitignore` に含まれているのでリポジトリには上がりません。

## 起動

```bash
uvicorn server:app --reload
```

ブラウザで `http://localhost:8000` を開く。

## API

| エンドポイント | 説明 |
|---|---|
| `GET /similar?word=孤独&topn=8` | 近い単語を返す |
| `GET /distant?word=孤独&topn=8` | 遠い単語を返す |
| `GET /similarity?word1=霧&word2=煙` | 2単語の類似度を返す |
| `GET /prompt?pivot=孤独&near=静寂,余白&far=賑わい,祭り&mode=combo` | Claude APIでプロンプトを生成する |

`mode` は `near`・`far`・`combo` の3種類。