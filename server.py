import os
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

def build_tone_line(tone: dict) -> str:
    parts = []
    for axis, val in tone.items():
        v = int(val)
        if v != 0 and axis in TONE_MAP and v in TONE_MAP[axis]:
            parts.append(TONE_MAP[axis][v])
    return f"- Tone / atmosphere: {', '.join(parts)}" if parts else ""

class PromptRequest(BaseModel):
    pivot: str
    near: list[str]
    far: list[str]
    mode: str = "combo"
    style: str = ""
    keywords: list[str] = []
    path: list[str] = []
    tone: dict = {}

class JourneyRequest(BaseModel):
    start: str
    end: str
    steps: int = 4

class AnalyzeRequest(BaseModel):
    text: str

class ExpandRequest(BaseModel):
    text: str
    style: str = ""
    keywords: list[str] = []
    topn: int = 5
    tone: dict = {}

class ArithmeticRequest(BaseModel):
    positive: list[str] = []
    negative: list[str] = []
    topn: int = 8

class EvaluateRequest(BaseModel):
    prompt: str
    scene_ja: str = ""

load_dotenv()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

model = KeyedVectors.load(os.environ["MODEL_PATH"])
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

tagger = fugashi.Tagger()

def missing(*words):
    """未登録単語があれば {"error": ...} を返す。なければ None。"""
    for w in words:
        if w not in model:
            return {"error": f"「{w}」が見つかりません"}
    return None

_jp = re.compile(r'[\u3040-\u9fff]')
_random_vocab = [w for w in list(model.key_to_index)[:50000] if len(w) >= 2 and _jp.search(w)]

@app.get("/random")
def random_word():
    return {"word": random.choice(_random_vocab)}

@app.get("/similar")
def similar(word: str, topn: int = 10):
    if err := missing(word): return err
    raw = model.most_similar(word, topn=topn * 3)
    random.shuffle(raw)
    return {"results": raw[:topn]}

@app.get("/distant")
def distant(word: str, topn: int = 10):
    if err := missing(word): return err
    raw = model.most_similar(negative=[word], topn=topn * 3)
    random.shuffle(raw)
    return {"results": raw[:topn]}

@app.get("/similarity")
def similarity(word1: str, word2: str):
    if err := missing(word1, word2): return err
    return {"score": float(model.similarity(word1, word2))}

@app.post("/prompt")
def generate_prompt(req: PromptRequest):
    if req.mode == "journey":
        if not req.path:
            return {"error": "journey モードには path が必要です"}
        instruction = f"「{req.path[0]}」から「{req.path[-1]}」へと意味が移ろう情景を作ってください。経路の単語を情景の変化として使ってください。経路: {' → '.join(req.path)}"
    elif req.mode == "near":
        instruction = f"「{req.pivot}」と意味的に近い雰囲気を活かした情景を作ってください。近い単語: {', '.join(req.near)}"
    elif req.mode == "far":
        instruction = f"「{req.pivot}」と対極にある要素を組み合わせた意外な情景を作ってください。対極の単語: {', '.join(req.far)}"
    elif req.mode == "combo":
        instruction = f"「{req.pivot}」を中心に、近い単語と遠い単語を意外な形で組み合わせてください。近い: {', '.join(req.near)} / 遠い: {', '.join(req.far)}"
    else:
        return {"error": f"不明なモードです: {req.mode}"}
    style_line = f"- Art style / medium: {req.style}" if req.style else ""
    keyword_line = f"- Must include these concepts: {', '.join(req.keywords)}" if req.keywords else ""
    tone_line = build_tone_line(req.tone)
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": f"""You are a prompt engineer for AI image generation.

Semantic instruction (Japanese):
{instruction}
{style_line}
{keyword_line}
{tone_line}

Output exactly 2 lines, no extra text:
Line 1 — SCENE: <具体的な情景を日本語で1000字以内に記述>
Line 2 — PROMPT: <English comma-separated tags, 120-500 words, specific and visual, subject/composition/environment/lighting/time/mood>"""
            }]
        )
    except Exception as e:
        return {"error": f"プロンプト生成に失敗しました: {e}"}
    raw = message.content[0].text
    scene_ja, prompt = "", raw
    for line in raw.splitlines():
        if line.startswith("SCENE:"):
            scene_ja = line[len("SCENE:"):].strip()
        elif line.startswith("PROMPT:"):
            prompt = line[len("PROMPT:"):].strip()
    return {"prompt": prompt, "scene_ja": scene_ja}

@app.post("/arithmetic")
def arithmetic(req: ArithmeticRequest):
    if not req.positive and not req.negative:
        return {"error": "単語を入力してください"}
    if err := missing(*req.positive, *req.negative): return err
    raw = model.most_similar(positive=req.positive or None, negative=req.negative or None, topn=req.topn * 3)
    exclude = set(req.positive + req.negative)
    filtered = [(w, s) for w, s in raw if w not in exclude]
    random.shuffle(filtered)
    return {"results": filtered[:req.topn]}

@app.post("/journey")
def journey(req: JourneyRequest):
    if err := missing(req.start, req.end): return err
    if req.start == req.end:
        return {"error": "起点と終点が同じ単語です"}

    start_vec = model[req.start]
    end_vec   = model[req.end]
    visited = {req.start, req.end}
    path = [req.start]

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
    extracted = []
    for word in tagger(req.text):
        pos = word.feature.pos1
        surface = word.surface
        if pos in ["名詞", "形容詞", "動詞"] and len(surface) >= 2 and surface in model:
            extracted.append(surface)
    extracted = list(dict.fromkeys(extracted))[:6]

    if not extracted:
        return {"error": "モデルに登録された単語が見つかりませんでした"}

    word_map = {}
    for w in extracted:
        word_map[w] = [s for s, _ in model.most_similar(w, topn=req.topn)][:req.topn]

    context_lines = "\n".join(
        f"・{w}: {', '.join(neighbors)}" for w, neighbors in word_map.items()
    )
    style_line = f"- Art style / medium: {req.style}" if req.style else ""
    keyword_line = f"- Must include these concepts: {', '.join(req.keywords)}" if req.keywords else ""
    tone_line = build_tone_line(req.tone)
    try:
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": f"""You are a prompt engineer for AI image generation.

Word clusters (Japanese semantic space):
{context_lines}
{style_line}
{keyword_line}
{tone_line}

Output exactly 2 lines, no extra text:
Line 1 — SCENE: <具体的な情景を日本語で1000字以内に記述>
Line 2 — PROMPT: <English comma-separated tags, 120-500 words, specific and visual, subject/composition/environment/lighting/time/mood>"""
            }]
        )
    except Exception as e:
        return {"error": f"プロンプト生成に失敗しました: {e}"}

    raw = message.content[0].text
    scene_ja, prompt = "", raw
    for line in raw.splitlines():
        if line.startswith("SCENE:"):
            scene_ja = line[len("SCENE:"):].strip()
        elif line.startswith("PROMPT:"):
            prompt = line[len("PROMPT:"):].strip()
    return {"words": extracted, "word_map": word_map, "prompt": prompt, "scene_ja": scene_ja}

@app.post("/evaluate")
def evaluate_prompt(req: EvaluateRequest):
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

@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    words = []
    for word in tagger(req.text):
        pos = word.feature.pos1
        surface = word.surface
        if pos in ["名詞", "形容詞", "動詞"] and len(surface) >= 2:
            words.append(surface)
    return {"words": list(set(words))}

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))