import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from gensim.models import KeyedVectors
from dotenv import load_dotenv
import anthropic
import fugashi
from pydantic import BaseModel

class PromptRequest(BaseModel):
    pivot: str
    near: list[str]
    far: list[str]
    mode: str = "combo"

class AnalyzeRequest(BaseModel):
    text: str

load_dotenv()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

model = KeyedVectors.load(os.environ["MODEL_PATH"])
client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

tagger = fugashi.Tagger()

@app.get("/similar")
def similar(word: str, topn: int = 10):
    if word not in model:
        return {"error": "単語が見つかりません"}
    return {"results": model.most_similar(word, topn=topn)}

@app.get("/distant")
def distant(word: str, topn: int = 10):
    if word not in model:
        return {"error": "単語が見つかりません"}
    return {"results": model.most_similar(negative=[word], topn=topn)}

@app.get("/similarity")
def similarity(word1: str, word2: str):
    if word1 not in model or word2 not in model:
        return {"error": "単語が見つかりません"}
    return {"score": float(model.similarity(word1, word2))}

@app.post("/prompt")
def generate_prompt(req: PromptRequest):
    instructions = {
        "near": f"「{req.pivot}」と意味的に近い雰囲気を活かした情景を作ってください。近い単語: {', '.join(req.near)}",
        "far":  f"「{req.pivot}」と対極にある要素を組み合わせた意外な情景を作ってください。対極の単語: {', '.join(req.far)}",
        "combo": f"「{req.pivot}」を中心に、近い単語と遠い単語を意外な形で組み合わせてください。近い: {', '.join(req.near)} / 遠い: {', '.join(req.far)}",
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
- 500文字以内
- プロンプト文だけ返す。説明や前置きは不要"""
        }]
    )
    return {"prompt": message.content[0].text}

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