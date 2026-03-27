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

class PromptRequest(BaseModel):
    pivot: str
    near: list[str]
    far: list[str]
    mode: str = "combo"
    style: str = ""
    keywords: list[str] = []
    path: list[str] = []

class JourneyRequest(BaseModel):
    start: str
    end: str
    steps: int = 4

class AnalyzeRequest(BaseModel):
    text: str

class ArithmeticRequest(BaseModel):
    positive: list[str] = []
    negative: list[str] = []
    topn: int = 8

load_dotenv()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

model = KeyedVectors.load(os.environ["MODEL_PATH"])
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

tagger = fugashi.Tagger()

@app.get("/similar")
def similar(word: str, topn: int = 10):
    if word not in model:
        return {"error": "単語が見つかりません"}
    raw = model.most_similar(word, topn=topn * 3)
    random.shuffle(raw)
    return {"results": raw[:topn]}

@app.get("/distant")
def distant(word: str, topn: int = 10):
    if word not in model:
        return {"error": "単語が見つかりません"}
    raw = model.most_similar(negative=[word], topn=topn * 3)
    random.shuffle(raw)
    return {"results": raw[:topn]}

@app.get("/similarity")
def similarity(word1: str, word2: str):
    if word1 not in model or word2 not in model:
        return {"error": "単語が見つかりません"}
    return {"score": float(model.similarity(word1, word2))}

@app.post("/prompt")
def generate_prompt(req: PromptRequest):
    instructions = {
        "near":    f"「{req.pivot}」と意味的に近い雰囲気を活かした情景を作ってください。近い単語: {', '.join(req.near)}",
        "far":     f"「{req.pivot}」と対極にある要素を組み合わせた意外な情景を作ってください。対極の単語: {', '.join(req.far)}",
        "combo":   f"「{req.pivot}」を中心に、近い単語と遠い単語を意外な形で組み合わせてください。近い: {', '.join(req.near)} / 遠い: {', '.join(req.far)}",
        "journey": f"「{req.path[0]}」から「{req.path[-1]}」へと意味が移ろう情景を作ってください。経路の単語を情景の変化として使ってください。経路: {' → '.join(req.path)}",
    }
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        messages=[{
            "role": "user",
            "content": f"""画像生成AIのプロンプトを日本語で1つ作ってください。

{instructions[req.mode]}

条件:
- 情景や雰囲気が浮かぶ詩的な文にする
{"- スタイル指定: " + req.style + "の画風で表現する" if req.style else ""}
{"- 以下の単語を必ずプロンプトに含める: " + "、".join(req.keywords) if req.keywords else ""}
- 500文字以内
- プロンプト文だけ返す。説明や前置きは不要"""
        }]
    )
    return {"prompt": message.content[0].text}

@app.post("/arithmetic")
def arithmetic(req: ArithmeticRequest):
    if not req.positive and not req.negative:
        return {"error": "単語を入力してください"}
    for w in req.positive + req.negative:
        if w not in model:
            return {"error": f"「{w}」が見つかりません"}
    raw = model.most_similar(positive=req.positive or None, negative=req.negative or None, topn=req.topn * 3)
    exclude = set(req.positive + req.negative)
    filtered = [(w, s) for w, s in raw if w not in exclude]
    random.shuffle(filtered)
    return {"results": filtered[:req.topn]}

@app.post("/journey")
def journey(req: JourneyRequest):
    if req.start not in model:
        return {"error": f"「{req.start}」が見つかりません"}
    if req.end not in model:
        return {"error": f"「{req.end}」が見つかりません"}
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