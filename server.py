import os
import json
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from gensim.models import KeyedVectors
from dotenv import load_dotenv
import anthropic
import fugashi
from pydantic import BaseModel
import random
import re

# 各トーン軸に対して、-3〜+3 の値を英語の形容詞フレーズにマッピングするテーブル。
# 値が 0 のときは使用しない。
TONE_MAP: dict[str, dict[int, str]] = {
    "brightness": {-3: "pitch black and lightless", -2: "very dark and gloomy", -1: "dim and shadowy", 1: "bright and luminous", 2: "radiant and dazzling", 3: "blindingly brilliant"},
    "quietness":  {-3: "turbulent and chaotic", -2: "chaotic and loud", -1: "lively and dynamic", 1: "quiet and calm", 2: "serene and silent", 3: "deeply hushed and still"},
    "mystery":    {-3: "completely mundane and everyday", -2: "mundane and ordinary", -1: "familiar and realistic", 1: "mysterious and uncanny", 2: "otherworldly and surreal", 3: "ethereal and transcendent"},
    "warmth":     {-3: "extreme cold and arctic", -2: "freezing and icy", -1: "cool and crisp", 1: "warm and cozy", 2: "scorching and blazing", 3: "searing and volcanic"},
    "era":        {-3: "primordial and prehistoric", -2: "ancient and archaic", -1: "historical and vintage", 1: "near-future", 2: "sci-fi future", 3: "far-future and post-human"},
    "scale":      {-3: "microscopic and tiny", -2: "small and intimate", -1: "compact and contained", 1: "vast and expansive", 2: "grand and monumental", 3: "cosmic and infinite"},
    "density":    {-3: "sparse and empty", -2: "open and airy", -1: "slightly sparse", 1: "somewhat dense", 2: "cluttered and intricate", 3: "overwhelmingly dense"},
    "decay":      {-3: "brand new and pristine", -2: "fresh and untouched", -1: "slightly aged", 1: "weathered and worn", 2: "ruined and abandoned", 3: "collapsed and crumbled"},
    "mood":       {-3: "peaceful and healing", -2: "calm and soothing", -1: "gentle and pleasant", 1: "slightly ominous", 2: "dark and foreboding", 3: "terrifying and dreadful"},
    "color":      {-3: "monochrome and desaturated", -2: "faded and pale", -1: "muted and subdued", 1: "vivid and colorful", 2: "rich and saturated", 3: "intensely chromatic"},
    "lighting":   {-3: "no light source, pitch black", -2: "faint moonlight or candlelight", -1: "dim indirect light", 1: "soft diffused light", 2: "dramatic directional light, backlit or side-lit", 3: "intense god rays or radiant spotlight"},
    "spatial":    {-3: "sealed and claustrophobic, no escape", -2: "enclosed and confined", -1: "intimate and sheltered", 1: "open and airy", 2: "vast sweeping landscape", 3: "infinite boundless horizon"},
    "clarity":    {-3: "thick impenetrable fog, zero visibility", -2: "heavy mist and haze", -1: "slightly hazy and atmospheric", 1: "clear and crisp air", 2: "crystal clear visibility", 3: "hyper-sharp and razor-clear"},
}

# プロンプト生成モードごとの指示文テンプレート。
# 毎回ランダムに1つ選ぶことで、同じ入力でも多様な出力を得る。
# キー: "near"（類似語活用）、"far"（対極語活用）、"combo"（両方を組み合わせ）、"journey"（単語間の旅）
_INSTRUCTIONS: dict[str, list[str]] = {
    "near": [
        "「{pivot}」と意味的に近い雰囲気を活かした情景を作ってください。近い単語: {near}",
        "「{pivot}」の世界観を深掘りし、{near} の質感を情景に溶かし込んでください",
        "「{pivot}」から連想される空間を、{near} の印象を手がかりに描写してください",
        "「{pivot}」に共鳴する情景を、{near} の雰囲気を軸に構築してください",
        "「{pivot}」の核にある感触を、{near} という言葉群を素材にして視覚化してください",
    ],
    "far": [
        "「{pivot}」と対極にある要素を組み合わせた意外な情景を作ってください。対極の単語: {far}",
        "「{pivot}」の対極にある {far} を衝突させ、予想外の情景を生み出してください",
        "「{pivot}」と {far} の矛盾を逆手に取り、緊張感のある情景を描いてください",
        "「{pivot}」が {far} の世界に迷い込んだとき、何が見えるかを描写してください",
        "「{pivot}」と {far} の間にある距離を、一枚の情景として表現してください",
    ],
    "combo": [
        "「{pivot}」を中心に、近い単語と遠い単語を意外な形で組み合わせてください。近い: {near} / 遠い: {far}",
        "「{pivot}」を核として、{near} の親密さと {far} の異質さが共存する情景を作ってください",
        "「{pivot}」の周囲に {near} を配置し、そこへ {far} を侵入させた情景を描いてください",
        "「{pivot}」を媒介に、{near} と {far} が予期せず交差する瞬間を切り取ってください",
        "「{pivot}」という起点から、{near} の方向と {far} の方向に同時に広がる情景を構成してください",
    ],
    "journey": [
        "「{start}」から「{end}」へと意味が移ろう情景を作ってください。経路の単語を情景の変化として使ってください。経路: {path}",
        "「{start}」を出発点に、{path} を経由して「{end}」へと変容する一続きの情景を描いてください",
        "「{start}」から「{end}」への旅を、{path} の各単語が場面転換の合図となるように描写してください",
        "「{start}」の空気が {path} を経て「{end}」へと溶けていく過程を、連続した情景として表現してください",
        "「{start}」→ {path} →「{end}」という意味の流れを、ひとつの情景が変容し続けるように描いてください",
    ],
}


def pick_instruction(mode: str, **kwargs) -> str:
    """指定モードの指示文テンプレートをランダムに選び、プレースホルダーを埋めて返す。

    Args:
        mode: 生成モード。"near" | "far" | "combo" | "journey" のいずれか。
        **kwargs: テンプレート内のプレースホルダーに対応するキーワード引数。
                  near/far/combo モードでは pivot・near・far、
                  journey モードでは start・end・path を渡す。

    Returns:
        プレースホルダーを埋めた日本語の指示文。
    """
    template = random.choice(_INSTRUCTIONS[mode])
    return template.format(**kwargs)


def build_extra_lines(style: str, keywords: list[str], tone: dict) -> str:
    """スタイル・キーワード・トーン指示を Claude プロンプト用の追加行にまとめて返す。

    Args:
        style: アートスタイル・画材（空文字なら省略）。
        keywords: 必ず含めるコンセプトのリスト（空なら省略）。
        tone: トーン軸名 → 強度値の辞書。

    Returns:
        有効な行を改行でつないだ文字列。すべて空なら空文字列。
    """
    lines = [
        f"- Art style / medium: {style}" if style else "",
        f"- Must include these concepts: {', '.join(keywords)}" if keywords else "",
        build_tone_line(tone),
    ]
    return "\n".join(l for l in lines if l)


def parse_scene_and_prompt(raw: str) -> tuple[str, str]:
    """Claude の応答から SCENE: 行と PROMPT: 行を取り出す。

    Args:
        raw: Claude が返した応答テキスト全体。

    Returns:
        (scene_ja, prompt) のタプル。
        各行が見つからない場合は scene_ja が空文字列、prompt が raw 全体になる。
    """
    scene_ja, prompt = "", raw
    for line in raw.splitlines():
        if line.startswith("SCENE:"):
            scene_ja = line[len("SCENE:"):].strip()
        elif line.startswith("PROMPT:"):
            prompt = line[len("PROMPT:"):].strip()
    return scene_ja, prompt


def build_tone_line(tone: dict) -> str:
    """tone 辞書（軸名 → -3〜3 の整数値）を、Claude へ渡す英語の雰囲気指示行に変換する。

    値が 0 の軸、または TONE_MAP に存在しない軸は無視する。

    Args:
        tone: トーン軸名をキー、強度値（-3〜3 の整数）を値とする辞書。

    Returns:
        有効な軸が1つ以上あれば "- Tone / atmosphere: ..." 形式の文字列、
        なければ空文字列。
    """
    parts = []
    for axis, val in tone.items():
        v = int(val)
        if v != 0 and axis in TONE_MAP and v in TONE_MAP[axis]:
            parts.append(TONE_MAP[axis][v])
    return f"- Tone / atmosphere: {', '.join(parts)}" if parts else ""

# --- リクエストスキーマ ---

class PromptRequest(BaseModel):
    """POST /prompt のリクエスト。pivot を中心に near/far の単語群からプロンプトを生成する。"""
    pivot: str
    near: list[str]
    far: list[str]
    mode: str = "combo"   # "near" | "far" | "combo" | "journey"
    style: str = ""        # 画風・媒体の指定（例: "oil painting"）
    keywords: list[str] = []  # 必ず含めるコンセプト
    path: list[str] = []  # journey モード用の経路単語リスト
    tone: dict = {}        # トーン軸 → 強度値（-3〜3）

class JourneyRequest(BaseModel):
    """POST /journey のリクエスト。start〜end 間を word2vec ベクトル補間で探索する。"""
    start: str
    end: str
    steps: int = 4  # start と end の間に挿入する中間単語数

class AnalyzeRequest(BaseModel):
    """POST /analyze のリクエスト。日本語テキストから名詞・形容詞・動詞を抽出する。"""
    text: str

class ExpandRequest(BaseModel):
    """POST /expand のリクエスト。日本語テキストを意味的に展開してプロンプトを生成する。"""
    text: str
    style: str = ""
    keywords: list[str] = []
    topn: int = 5   # 各単語から取得する類似語の数
    tone: dict = {}

class ArithmeticRequest(BaseModel):
    """POST /arithmetic のリクエスト。単語ベクトルの加減算で類似語を探索する。"""
    positive: list[str] = []  # 加算する単語リスト
    negative: list[str] = []  # 減算する単語リスト
    topn: int = 8

class EvaluateRequest(BaseModel):
    """POST /evaluate のリクエスト。英語プロンプトの品質をスコアリングする。"""
    prompt: str
    scene_ja: str = ""  # 日本語の情景説明（省略可）

class ClusterRequest(BaseModel):
    """POST /cluster のリクエスト。複数単語の共通近傍語を探索する。"""
    words: list[str]        # 2語以上必須
    topn: int = 10

load_dotenv()

# 日本標準時（UTC+9）
JST = timezone(timedelta(hours=9))

# ログの出力先パス（環境変数 LOG_PATH で上書き可）
LOG_PATH = os.environ.get("LOG_PATH", "prompts.log")

def write_log(endpoint: str, params: dict, scene_ja: str, prompt: str):
    """生成結果を JSONL 形式でログファイルに追記する。

    Args:
        endpoint: 呼び出し元のエンドポイントパス（例: "/prompt"）。
        params: リクエストパラメータ全体の辞書。
        scene_ja: 生成された日本語の情景説明。
        prompt: 生成された英語のプロンプトタグ列。
    """
    entry = {
        "timestamp": datetime.now(JST).isoformat(),
        "endpoint": endpoint,
        "params": params,
        "scene_ja": scene_ja,
        "prompt": prompt,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

app = FastAPI()
# フロントエンド（任意のオリジン）からの API 呼び出しを許可する
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# word2vec モデルの読み込み（起動時に一度だけ実行）
model = KeyedVectors.load(os.environ["MODEL_PATH"])
# Anthropic クライアントの初期化
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# 日本語形態素解析器の初期化
tagger = fugashi.Tagger()

def missing(*words):
    """未登録単語があれば {"error": ...} を返す。なければ None。

    Args:
        *words: word2vec モデルへの登録有無を確認する単語（可変長）。

    Returns:
        未登録単語が1つでもあれば {"error": "「{word}」が見つかりません"} の辞書、
        すべて登録済みであれば None。
    """
    for w in words:
        if w not in model:
            return {"error": f"「{w}」が見つかりません"}
    return None

# ランダム単語候補: 語彙先頭50000語から、日本語を含む2文字以上の単語のみ抽出
_jp = re.compile(r'[\u3040-\u9fff]')
_random_vocab = [w for w in list(model.key_to_index)[:50000] if len(w) >= 2 and _jp.search(w)]

@app.get("/random")
def random_word():
    """語彙から日本語単語をランダムに1つ返す。

    Returns:
        {"word": str} — ランダムに選ばれた日本語単語。
    """
    return {"word": random.choice(_random_vocab)}

@app.get("/similar")
def similar(word: str, topn: int = 10):
    """word に意味的に近い単語を topn 件返す。結果はシャッフルして多様性を出す。

    Args:
        word: 検索対象の単語。
        topn: 返す類似語の件数（デフォルト 10）。

    Returns:
        {"results": [(単語, コサイン類似度), ...]} または {"error": str}。
    """
    if err := missing(word): return err
    raw = model.most_similar(word, topn=topn * 3)
    random.shuffle(raw)
    return {"results": raw[:topn]}

@app.get("/distant")
def distant(word: str, topn: int = 10):
    """word と意味的に遠い（対極の）単語を topn 件返す。結果はシャッフルして多様性を出す。

    Args:
        word: 検索対象の単語。
        topn: 返す対極語の件数（デフォルト 10）。

    Returns:
        {"results": [(単語, コサイン類似度), ...]} または {"error": str}。
    """
    if err := missing(word): return err
    raw = model.most_similar(negative=[word], topn=topn * 3)
    random.shuffle(raw)
    return {"results": raw[:topn]}

@app.get("/similarity")
def similarity(word1: str, word2: str):
    """2つの単語間のコサイン類似度（-1〜1）を返す。

    Args:
        word1: 比較する単語（一方）。
        word2: 比較する単語（もう一方）。

    Returns:
        {"score": float} — コサイン類似度（-1〜1）または {"error": str}。
    """
    if err := missing(word1, word2): return err
    return {"score": float(model.similarity(word1, word2))}

@app.post("/prompt")
def generate_prompt(req: PromptRequest):
    """pivot・near/far 単語・モードをもとに Claude で画像生成プロンプトを生成する。

    Args:
        req: PromptRequest — pivot・near・far・mode・style・keywords・path・tone を含む。

    Returns:
        {"prompt": str, "scene_ja": str} — 英語タグ列と日本語情景説明、
        またはエラー時 {"error": str}。
    """
    # モードに応じて Claude への指示文を組み立てる
    if req.mode == "journey":
        if not req.path:
            return {"error": "journey モードには path が必要です"}
        instruction = pick_instruction("journey",
            start=req.path[0], end=req.path[-1], path=" → ".join(req.path))
    elif req.mode == "near":
        instruction = pick_instruction("near",
            pivot=req.pivot, near=", ".join(req.near))
    elif req.mode == "far":
        instruction = pick_instruction("far",
            pivot=req.pivot, far=", ".join(req.far))
    elif req.mode == "combo":
        instruction = pick_instruction("combo",
            pivot=req.pivot, near=", ".join(req.near), far=", ".join(req.far))
    else:
        return {"error": f"不明なモードです: {req.mode}"}
    extra = build_extra_lines(req.style, req.keywords, req.tone)
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": f"""You are a prompt engineer for AI image generation.

Semantic instruction (Japanese):
{instruction}
{extra}

Output exactly 2 lines, no extra text:
Line 1 — SCENE: <具体的な情景を日本語で1000字以内に記述>
Line 2 — PROMPT: <English comma-separated tags, 100-300 words, concise and selective, only the most essential and evocative details for subject/composition/lighting/mood>"""
            }]
        )
    except Exception as e:
        return {"error": f"プロンプト生成に失敗しました: {e}"}
    scene_ja, prompt = parse_scene_and_prompt(message.content[0].text)
    write_log("/prompt", {"pivot": req.pivot, "near": req.near, "far": req.far, "mode": req.mode, "style": req.style, "keywords": req.keywords, "path": req.path, "tone": req.tone}, scene_ja, prompt)
    return {"prompt": prompt, "scene_ja": scene_ja}

@app.post("/arithmetic")
def arithmetic(req: ArithmeticRequest):
    """単語ベクトルの加減算（例: 王 - 男 + 女 ≈ 女王）で関連語を返す。

    positive/negative の単語自体は結果から除外する。

    Args:
        req: ArithmeticRequest — positive（加算語リスト）・negative（減算語リスト）・topn。

    Returns:
        {"results": [(単語, スコア), ...]} — 入力語を除いたシャッフル済み類似語リスト、
        またはエラー時 {"error": str}。
    """
    if not req.positive and not req.negative:
        return {"error": "単語を入力してください"}
    if err := missing(*req.positive, *req.negative): return err
    raw = model.most_similar(positive=req.positive or None, negative=req.negative or None, topn=req.topn * 3)
    # 入力単語が結果に混入しないようフィルタリングしてからシャッフル
    exclude = set(req.positive + req.negative)
    filtered = [(w, s) for w, s in raw if w not in exclude]
    random.shuffle(filtered)
    return {"results": filtered[:req.topn]}

@app.post("/journey")
def journey(req: JourneyRequest):
    """start〜end 間をベクトル線形補間で探索し、意味的な「旅の経路」となる単語列を返す。

    補間点ごとに最近傍の未訪問単語を選ぶことで、重複なく自然な経路を生成する。

    Args:
        req: JourneyRequest — start（起点）・end（終点）・steps（中間ステップ数）。

    Returns:
        {"path": [str, ...]} — [start, 中間語, ..., end] の単語リスト、
        またはエラー時 {"error": str}。
    """
    if err := missing(req.start, req.end): return err
    if req.start == req.end:
        return {"error": "起点と終点が同じ単語です"}

    start_vec = model[req.start]
    end_vec   = model[req.end]
    visited = {req.start, req.end}
    path = [req.start]

    # steps 個の中間点を線形補間で配置し、各点に最近傍単語を割り当てる
    for i in range(1, req.steps + 1):
        t = i / (req.steps + 1)
        interp = (1.0 - t) * start_vec + t * end_vec
        for word, _ in model.similar_by_vector(interp, topn=30):
            if word not in visited:
                path.append(word)
                visited.add(word)
                break

    path.append(req.end)
    return {"path": path}

@app.post("/expand")
def expand(req: ExpandRequest):
    """日本語テキストを形態素解析して主要語を抽出し、各語の類似語クラスタをもとに Claude でプロンプトを生成する。

    Args:
        req: ExpandRequest — text・style・keywords・topn・tone を含む。

    Returns:
        {"words": [str], "word_map": {str: [str]}, "prompt": str, "scene_ja": str} —
        抽出語・類似語マップ・英語タグ列・日本語情景説明、
        またはエラー時 {"error": str}。
    """
    # 名詞・形容詞・動詞のうち2文字以上でモデルに登録されている語を抽出（最大6語）
    extracted = []
    for word in tagger(req.text):
        pos = word.feature.pos1
        surface = word.surface
        if pos in ["名詞", "形容詞", "動詞"] and len(surface) >= 2 and surface in model:
            extracted.append(surface)
    extracted = list(dict.fromkeys(extracted))[:6]  # 出現順を保ちつつ重複排除

    if not extracted:
        return {"error": "モデルに登録された単語が見つかりませんでした"}

    # 各抽出語の類似語リストを取得
    word_map = {}
    for w in extracted:
        word_map[w] = [s for s, _ in model.most_similar(w, topn=req.topn)][:req.topn]

    context_lines = "\n".join(
        f"・{w}: {', '.join(neighbors)}" for w, neighbors in word_map.items()
    )
    extra = build_extra_lines(req.style, req.keywords, req.tone)
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": f"""You are a prompt engineer for AI image generation.

Word clusters (Japanese semantic space):
{context_lines}
{extra}

Output exactly 2 lines, no extra text:
Line 1 — SCENE: <具体的な情景を日本語で1000字以内に記述>
Line 2 — PROMPT: <English comma-separated tags, 40-80 words, concise and selective, only the most essential and evocative details for subject/composition/lighting/mood>"""
            }]
        )
    except Exception as e:
        return {"error": f"プロンプト生成に失敗しました: {e}"}
    scene_ja, prompt = parse_scene_and_prompt(message.content[0].text)
    write_log("/expand", {"text": req.text, "style": req.style, "keywords": req.keywords, "topn": req.topn, "tone": req.tone}, scene_ja, prompt)
    return {"words": extracted, "word_map": word_map, "prompt": prompt, "scene_ja": scene_ja}

@app.post("/evaluate")
def evaluate_prompt(req: EvaluateRequest):
    """英語プロンプトを Claude で評価し、総合スコア・5次元スコア・改善提案を返す。

    Args:
        req: EvaluateRequest — prompt（英語プロンプト）・scene_ja（日本語情景説明、省略可）。

    Returns:
        {
            "score": int,                          # 総合スコア（0〜100）
            "dimensions": {                        # 各次元のスコア（0〜10）
                "subject": int,
                "composition": int,
                "lighting": int,
                "mood": int,
                "detail": int,
            },
            "suggestions": [str, ...],             # 日本語の改善提案（最大3件）
        }
        またはエラー時 {"error": str}。
    """
    if not req.prompt or len(req.prompt.strip()) < 10:
        return {"error": "プロンプトが短すぎます"}
    scene_line = f"\nJapanese scene description:\n{req.scene_ja}" if req.scene_ja else ""
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=600,
            messages=[{
                "role": "user",
                "content": f"""You are an expert evaluator of AI image generation prompts.

Evaluate the following prompt for AI image generation quality.

English prompt:
{req.prompt}{scene_line}

Output exactly in this format (no extra text, no markdown):
SCORE: <0-100 overall score>
SUBJECT: <0-10 subject clarity score>
COMPOSITION: <0-10 composition/framing score>
LIGHTING: <0-10 lighting quality score>
MOOD: <0-10 atmosphere/mood score>
DETAIL: <0-10 specificity/detail score>
SUGGESTIONS:
・<concrete improvement suggestion in Japanese, 1 sentence>
・<concrete improvement suggestion in Japanese, 1 sentence>
・<concrete improvement suggestion in Japanese, 1 sentence>"""
            }]
        )
    except Exception as e:
        return {"error": f"評価に失敗しました: {e}"}

    # Claude の応答を行ごとにパースして結果辞書に格納する
    raw = message.content[0].text
    result: dict = {"score": 0, "dimensions": {}, "suggestions": []}
    in_suggestions = False
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("SCORE:"):
            try: result["score"] = int(line.split(":", 1)[1].strip())
            except: pass
        elif line.startswith("SUBJECT:"):
            try: result["dimensions"]["subject"] = int(line.split(":", 1)[1].strip())
            except: pass
        elif line.startswith("COMPOSITION:"):
            try: result["dimensions"]["composition"] = int(line.split(":", 1)[1].strip())
            except: pass
        elif line.startswith("LIGHTING:"):
            try: result["dimensions"]["lighting"] = int(line.split(":", 1)[1].strip())
            except: pass
        elif line.startswith("MOOD:"):
            try: result["dimensions"]["mood"] = int(line.split(":", 1)[1].strip())
            except: pass
        elif line.startswith("DETAIL:"):
            try: result["dimensions"]["detail"] = int(line.split(":", 1)[1].strip())
            except: pass
        elif line == "SUGGESTIONS:":
            in_suggestions = True
        elif in_suggestions and line.startswith("・"):
            result["suggestions"].append(line[1:].strip())
    return result

@app.post("/cluster")
def cluster(req: ClusterRequest):
    """複数単語すべてに意味的に近い共通近傍語を返す。

    入力単語ベクトルの重心（centroid）に最も近い単語を探索し、
    入力単語自身は結果から除外したうえでシャッフルして返す。

    Args:
        req: ClusterRequest — words（2語以上）・topn。

    Returns:
        {"results": [(単語, スコア), ...]} または {"error": str}。
    """
    if len(req.words) < 2:
        return {"error": "2語以上入力してください"}
    if err := missing(*req.words): return err
    raw = model.most_similar(positive=req.words, topn=req.topn * 3)
    exclude = set(req.words)
    filtered = [(w, s) for w, s in raw if w not in exclude]
    random.shuffle(filtered)
    return {"results": filtered[:req.topn]}


@app.get("/history")
def get_history(limit: int = 50, offset: int = 0, q: str = ""):
    """prompts.log から生成履歴を新着順で返す。

    Args:
        limit: 返す最大件数（デフォルト 50）。
        offset: スキップする件数（ページネーション用）。
        q: 絞り込みクエリ（scene_ja・prompt に部分一致する行のみ返す）。

    Returns:
        {"entries": [...], "total": int} —
        一致エントリの配列と総件数。entry の構造は write_log の出力と同じ。
    """
    limit = min(limit, 200)
    q_lower = q.lower() if q else ""

    try:
        with open(LOG_PATH, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return {"entries": [], "total": 0}

    matched = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if q_lower and q_lower not in entry.get("scene_ja", "").lower() \
                   and q_lower not in entry.get("prompt", "").lower():
            continue
        matched.append(entry)

    return {"entries": matched[offset: offset + limit], "total": len(matched)}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    """日本語テキストから名詞・形容詞・動詞（2文字以上）を抽出して返す。

    /expand の事前確認用途を想定。word2vec への登録有無は問わない。

    Args:
        req: AnalyzeRequest — text（解析対象の日本語テキスト）。

    Returns:
        {"words": [str, ...]} — 重複を除いた抽出語リスト。
    """
    words = []
    for word in tagger(req.text):
        pos = word.feature.pos1
        surface = word.surface
        if pos in ["名詞", "形容詞", "動詞"] and len(surface) >= 2:
            words.append(surface)
    return {"words": list(set(words))}

# 静的ファイル（フロントエンド）をルートにマウント
app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
