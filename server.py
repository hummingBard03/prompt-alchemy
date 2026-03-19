from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from gensim.models import KeyedVectors

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

model = KeyedVectors.load("chive-1.3-mc90.kv")

@app.get("/similar")
def similar(word: str, topn: int = 10):
    if word not in model:
        return {"error": "単語が見つかりません"}
    results = model.most_similar(word, topn=topn)
    return {"results": results}

@app.get("/distant")
def distant(word: str, topn: int = 10):
    if word not in model:
        return {"error": "単語が見つかりません"}
    results = model.most_similar(negative=[word], topn=topn)
    return {"results": results}

@app.get("/similarity")
def similarity(word1: str, word2: str):
    if word1 not in model or word2 not in model:
        return {"error": "単語が見つかりません"}
    score = model.similarity(word1, word2)
    return float(score)

# 最後にこれを追加（APIより後に書く）
app.mount("/", StaticFiles(directory=".", html=True), name="static")