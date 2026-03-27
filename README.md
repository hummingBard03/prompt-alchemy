# 錬語術 — Prompt Alchemy

Word2Vec を使って単語の意味空間を探索し、Claude API で画像生成プロンプトを生成するツール。

## 機能

| 機能 | 説明 |
|---|---|
| **単語展開** | 入力した単語に意味的に近い・遠い単語を Word2Vec で列挙する |
| **ベクトル演算** | `海 ＋ 光 － 暗闇` のように単語を合成・減算して新しい単語を発見する |
| **連想チェーン** | 起点から終点へ、ベクトル補間で意味的な経路を辿る（例: 孤独 → 静寂 → 深夜 → 都市 → 光） |
| **プロンプト生成** | 選んだ単語群や経路をもとに Claude API が詩的な画像生成プロンプトを作る |
| **単語抽出** | 生成されたプロンプトを形態素解析して、次の探索に使える単語を取り出す |

## 構成

```
prompt-alchemy/
├── server.py        # FastAPI サーバー（Word2Vec + Claude API + 形態素解析）
├── index.html       # UI
├── style.css        # スタイル
├── app.js           # フロントエンドロジック
├── requirements.txt # Python ライブラリ一覧
├── .env             # 環境変数（Git 管理外）
└── README.md
```

モデルファイル（`*.kv`, `*.kv.vectors.npy`）はサイズが大きいため Git 管理外。別途ダウンロードしてください。

## セットアップ

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## モデルのダウンロード

[chiVe](https://github.com/WorksApplications/chiVe) から任意のモデルをダウンロードしてプロジェクトのルートに置く。

```
chive-1.2-mc15.kv          # 軽量版（推奨）
chive-1.2-mc15.kv.vectors.npy
```

## 環境変数

`.env` をプロジェクトのルートに作成する：

```
ANTHROPIC_API_KEY=sk-ant-...
MODEL_PATH=chive-1.2-mc15.kv
```

`.env` は `.gitignore` に含まれているのでリポジトリには上がりません。

## 起動

```bash
uvicorn server:app --reload
```

ブラウザで `http://localhost:8000` を開く。

## API

| メソッド | エンドポイント | 説明 |
|---|---|---|
| GET | `/similar?word=孤独&topn=8` | 意味的に近い単語を返す |
| GET | `/distant?word=孤独&topn=8` | 意味的に遠い単語を返す |
| GET | `/similarity?word1=霧&word2=煙` | 2単語の類似度スコアを返す |
| POST | `/prompt` | Claude API でプロンプトを生成する |
| POST | `/arithmetic` | ベクトル演算で近い単語を返す |
| POST | `/journey` | 起点から終点への意味的経路を返す |
| POST | `/analyze` | テキストを形態素解析して単語リストを返す |

### POST /prompt

```json
{
  "pivot": "孤独",
  "near": ["静寂", "余白"],
  "far": ["賑わい", "祭り"],
  "mode": "combo",
  "style": "水彩画",
  "keywords": ["月", "廃墟"],
  "path": []
}
```

`mode` の種類:

| mode | 説明 |
|---|---|
| `near` | 近い単語の雰囲気でプロンプトを生成 |
| `far` | 対極の単語を組み合わせた意外な情景を生成 |
| `combo` | 近い・遠い単語を両方使って生成 |
| `journey` | `path` の経路を辿るように情景が移ろうプロンプトを生成 |

### POST /arithmetic

```json
{
  "positive": ["海", "光"],
  "negative": ["暗闇"],
  "topn": 8
}
```

- `positive`: 加算する単語リスト（1つ以上必須）
- `negative`: 減算する単語リスト（省略可）
- 入力単語は結果から除外される

### POST /journey

```json
{
  "start": "孤独",
  "end": "光",
  "steps": 4
}
```

起点と終点のベクトルを線形補間し、各中間点に最も近い単語を選んで経路を構築する。`steps` は中間語の数（デフォルト 4）。

### POST /analyze

```json
{ "text": "霧の中に孤独が佇む" }
```
