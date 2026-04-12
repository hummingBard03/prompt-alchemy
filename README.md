# 錬語術 — Prompt Alchemy

Word2Vec を使って単語の意味空間を探索し、Claude API で画像生成プロンプトを生成するツール。

## 機能

| 機能 | 説明 |
|---|---|
| **単語展開** | 入力した単語に意味的に近い・遠い単語を Word2Vec で列挙する |
| **ベクトル演算** | `海 ＋ 光 － 暗闇` のように単語を合成・減算して新しい単語を発見する |
| **連想チェーン** | 起点から終点へ、ベクトル補間で意味的な経路を辿る（例: 孤独 → 静寂 → 深夜 → 都市 → 光） |
| **プロンプト生成** | 選んだ単語群や経路をもとに Claude API が詩的な画像生成プロンプトを作る。トーン調整スライダーで明るさ・静けさ・神秘性・温度感・時代感を指定できる |
| **文章展開** | 文章を貼り付けると単語を自動抽出し、各単語の意味空間を束ねて一括でプロンプトを生成する |
| **単語抽出** | 生成されたプロンプトを形態素解析して、次の探索に使える単語を取り出す |
| **プロンプト品質評価** | 生成されたプロンプトを Claude API で評価し、0〜100 の総合スコア・5軸スコア（被写体・構図・光・雰囲気・詳細度）・改善提案を表示する |
| **生成履歴ブラウザ** | これまでに生成したプロンプトを一覧表示する。情景メモやプロンプト本文で絞り込み検索でき、コピー・品質評価・pivot 単語での再検索が行える |

## 構成

```
prompt-alchemy/
├── server.py        # FastAPI サーバー（Word2Vec + Claude API + 形態素解析）
├── index.html       # UI
├── style.css        # スタイル
├── app.js           # フロントエンドロジック
├── requirements.txt # Python ライブラリ一覧
├── prompts.log      # 生成プロンプトのログ（JSONL、Git 管理外）
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
PORT=8000
LOG_PATH=prompts.log
```

`LOG_PATH` は省略可。省略するとカレントディレクトリの `prompts.log` に書き込まれる。

`.env` は `.gitignore` に含まれているのでリポジトリには上がりません。

## 起動

```bash
python server.py
```

ブラウザで `http://localhost:8000` を開く。

## API

| メソッド | エンドポイント | 説明 |
|---|---|---|
| GET | `/random` | モデル語彙からランダムな単語を返す |
| GET | `/similar?word=孤独&topn=8` | 意味的に近い単語を返す |
| GET | `/distant?word=孤独&topn=8` | 意味的に遠い単語を返す |
| GET | `/similarity?word1=霧&word2=煙` | 2単語の類似度スコアを返す |
| GET | `/history?limit=50&offset=0&q=` | 生成履歴を新着順で返す。`q` で scene_ja・prompt を絞り込み |
| POST | `/prompt` | Claude API でプロンプトを生成する |
| POST | `/arithmetic` | ベクトル演算で近い単語を返す |
| POST | `/journey` | 起点から終点への意味的経路を返す |
| POST | `/analyze` | テキストを形態素解析して単語リストを返す |
| POST | `/expand` | テキストから単語を抽出し近傍語を展開して Claude API でプロンプトを生成する |
| POST | `/evaluate` | プロンプトを Claude API で評価し、スコア・5軸スコア・改善提案を返す |

#### GET /random

```json
{ "word": "夕暮れ" }
```

#### GET /similar, /distant

```json
{ "results": [["黄昏", 0.91], ["薄暮", 0.87], ...] }
```

#### GET /similarity

```json
{ "score": 0.83 }
```

### POST /prompt

```json
{
  "pivot": "孤独",
  "near": ["静寂", "余白"],
  "far": ["賑わい", "祭り"],
  "mode": "combo",
  "style": "水彩画",
  "keywords": ["月", "廃墟"],
  "path": [],
  "tone": { "brightness": -1, "mystery": 2 }
}
```

- `style`: アートスタイル・画材（省略可）
- `keywords`: 必ず含めたい概念のリスト（省略可）
- `path`: `journey` モード時に使用する経路の単語リスト

レスポンス:

```json
{
  "scene_ja": "具体的な情景の日本語説明",
  "prompt": "生成されたプロンプト文"
}
```

`tone` はトーン調整（省略可）。各軸に −3〜+3 の整数を指定する。0 または省略するとその軸は指示に含まれない。

| 軸 | −3 | −2 | −1 | +1 | +2 | +3 |
|---|---|---|---|---|---|---|
| `brightness` | 完全な暗闇 | 非常に暗い | やや暗い | 明るい | 輝かしい | 眩いほど明るい |
| `quietness` | 激しく混沌 | 非常に騒がしい | やや動的 | 静か | 穏やかな静寂 | 深い静寂 |
| `mystery` | 完全に日常的 | ありふれた | 写実的 | 神秘的 | 超現実的 | 幽玄・超越的 |
| `warmth` | 極寒・氷河 | 凍てつく | やや冷涼 | 温かい | 灼熱 | 溶岩のような熱 |
| `era` | 太古・先史 | 非常に古代的 | 歴史・古風 | 近未来 | SF的未来 | 遠未来・ポスト人類 |
| `scale` | 微細・極小 | 小さく親密 | コンパクト | 広大 | 壮大 | 宇宙的・無限 |
| `density` | 疎らで空虚 | 開放的 | やや疎ら | やや密 | 複雑に密集 | 圧倒的な密度 |
| `decay` | 真新しい | 清潔で未使用 | わずかに古い | 風化・劣化 | 廃墟・放置 | 崩壊・瓦礫 |
| `mood` | 平和・癒し | 穏やか | 優しい | やや不吉 | 暗く不穏 | 恐ろしく戦慄 |
| `color` | モノクロ・脱色 | 色褪せた | くすんだ | 鮮やか | 濃く飽和 | 強烈な色彩 |
| `lighting` | 暗闇・光源なし | 月明かり・蝋燭 | 薄い間接光 | 柔らかい拡散光 | 逆光・サイド光 | 神光・強烈スポット |
| `spatial` | 密閉・閉塞 | 狭い囲まれた空間 | こじんまりした | 開放的 | 広大な風景 | 無限の地平 |
| `clarity` | 濃霧・視界ゼロ | 深い霧・靄 | うっすら霞んだ | 澄んだ空気 | クリスタルクリア | 超鮮明・くっきり |

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

レスポンス:

```json
{ "words": ["霧", "孤独"] }
```

### POST /expand

```json
{
  "text": "夕暮れの港に錆びた船が浮かんでいた",
  "style": "水彩画",
  "keywords": ["夕焼け"],
  "topn": 5
}
```

- `text`: 展開元の文章（形態素解析で名詞・形容詞・動詞を最大6語抽出）
- `topn`: 各単語から取得する近傍語の数（デフォルト 5）
- `style`, `keywords`, `tone`: `/prompt` と同様

レスポンス:

```json
{
  "words": ["夕暮れ", "港", "船"],
  "word_map": { "夕暮れ": ["黄昏", "夕焼け", ...], ... },
  "scene_ja": "具体的な情景の日本語説明",
  "prompt": "生成されたプロンプト文"
}
```

### POST /evaluate

```json
{
  "prompt": "foggy harbor at dusk, muted tones, melancholic atmosphere, soft diffused light",
  "scene_ja": "霧に包まれた港の夕景"
}
```

- `prompt`: 評価する英語プロンプト（10文字以上必須）
- `scene_ja`: 日本語の情景メモ（省略可。指定するとより精度の高い評価が得られる）

レスポンス:

```json
{
  "score": 78,
  "dimensions": {
    "subject":     8,
    "composition": 7,
    "lighting":    8,
    "mood":        9,
    "detail":      6
  },
  "suggestions": [
    "前景に具体的な要素（錆びた桟橋や係留ロープなど）を加えると構図が安定します",
    "光源の方向（サイドライト・逆光など）を明示するとより劇的な画になります",
    "色温度（暖色系の夕焼けか寒色系の薄明かりか）を指定すると生成精度が上がります"
  ]
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| `score` | 整数 0〜100 | 総合品質スコア。80以上: 高品質、60〜79: 標準、59以下: 要改善 |
| `dimensions.subject` | 整数 0〜10 | 被写体の明確さ |
| `dimensions.composition` | 整数 0〜10 | 構図・フレーミング |
| `dimensions.lighting` | 整数 0〜10 | 光の質・方向・強度の記述 |
| `dimensions.mood` | 整数 0〜10 | 雰囲気・感情の表現 |
| `dimensions.detail` | 整数 0〜10 | 具体性・詳細度 |
| `suggestions` | 文字列リスト | 日本語による改善提案（最大3件） |
