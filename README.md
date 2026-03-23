# 錬語術 — Prompt Alchemy

Word2Vec を使って単語の「近い・遠い」を探索し、Claude API で画像生成プロンプトを生成するツール。生成されたプロンプトを形態素解析にかけて新しい単語を抽出する機能も持つ。

## 構成

```
prompt-alchemy/
├── server.py        # FastAPI サーバー（Word2Vec + Claude API + 形態素解析）
├── index.html       # UI
├── style.css        # スタイル
├── app.js           # フロントエンドロジック
├── requirements.txt # Pythonライブラリ一覧
├── .env             # 環境変数（Git管理外）
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

## 環境変数の設定

`.env` ファイルをプロジェクトのルートに作成する：

```
ANTHROPIC_API_KEY=sk-ant-...
MODEL_PATH=chive-1.2-mc90.kv
```
`ANTHROPIC_API_KEY`にはClaudeAPIのAPIキーを設定。
モデルファイルを変更したい場合は `MODEL_PATH` だけ書き換えればよい。`  
.env` は `.gitignore` に含まれているのでリポジトリには上がりません。

## 起動

```bash
uvicorn server:app --reload
```

ブラウザで `http://localhost:8000` を開く。

## API

| メソッド | エンドポイント | 説明 |
|---|---|---|
| GET | `/similar?word=孤独&topn=8` | 近い単語を返す |
| GET | `/distant?word=孤独&topn=8` | 遠い単語を返す |
| GET | `/similarity?word1=霧&word2=煙` | 2単語の類似度を返す |
| POST | `/prompt` | Claude API でプロンプトを生成する |
| POST | `/analyze` | テキストを形態素解析して単語リストを返す |

### POST /prompt

```json
{
  "pivot": "孤独",
  "near": ["静寂", "余白"],
  "far": ["賑わい", "祭り"],
  "mode": "combo",
  "style": "水彩画",
  "keywords": ["月", "廃墟"]
}
```

- `mode`: `near`・`far`・`combo` の3種類
- `style`: 画風の指定（省略可）。例: `油絵`、`印象派絵画`、`フィルム写真` など
- `keywords`: プロンプトに必ず含める単語リスト（省略可）

### POST /analyze

```json
{ "text": "霧の中に孤独が佇む" }
```