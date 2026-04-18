"""
サーバーのテスト（全エンドポイント）

モック対象:
  - server.model        : Word2Vec (gensim KeyedVectors)
  - server.client       : Anthropic クライアント
  - server.tagger       : fugashi Tagger
  - server._random_vocab: ランダム単語プール
"""

import json as _json
from pathlib import Path

import numpy as np
import pytest
import server as srv
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from server import TONE_MAP, build_tone_line, _INSTRUCTIONS, pick_instruction


# ── モックファクトリ ──────────────────────────────────────────────────────────

VOCAB = {"孤独", "静寂", "霧", "煙", "光", "賑わい", "夕暮れ", "港", "船"}


def make_model(vocab=VOCAB):
    m = MagicMock()
    m.__contains__ = lambda self, w: w in vocab
    m.key_to_index = {w: i for i, w in enumerate(vocab)}
    m.most_similar.return_value = [("霧", 0.9), ("煙", 0.85), ("静寂", 0.8), ("光", 0.75), ("港", 0.7)]
    m.similar_by_vector.return_value = [("煙", 0.88), ("霧", 0.82)]
    m.similarity.return_value = 0.75
    m.__getitem__ = lambda self, w: np.zeros(100, dtype=np.float32)
    return m


def make_client(scene="夕暮れの情景", prompt_text="foggy harbor, dusk, muted tones"):
    msg = MagicMock()
    msg.content = [MagicMock(text=f"SCENE: {scene}\nPROMPT: {prompt_text}")]
    c = MagicMock()
    c.messages.create.return_value = msg
    return c


def make_eval_client(score=75, subject=8, composition=7, lighting=8, mood=7, detail=6,
                     suggestions=None):
    if suggestions is None:
        suggestions = ["光源の方向を具体的に指定しましょう", "前景に要素を加えると構図が安定します", "色温度を明示すると精度が上がります"]
    sug_lines = "\n".join(f"・{s}" for s in suggestions)
    text = (
        f"SCORE: {score}\n"
        f"SUBJECT: {subject}\n"
        f"COMPOSITION: {composition}\n"
        f"LIGHTING: {lighting}\n"
        f"MOOD: {mood}\n"
        f"DETAIL: {detail}\n"
        f"SUGGESTIONS:\n{sug_lines}"
    )
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    c = MagicMock()
    c.messages.create.return_value = msg
    return c


def make_word(surface, pos1):
    w = MagicMock()
    w.surface = surface
    w.feature.pos1 = pos1
    return w


def make_tagger(words):
    t = MagicMock()
    t.return_value = words
    return t


# ── フィクスチャ ──────────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path):
    import server as srv

    orig = (srv.model, srv.client, srv.tagger, srv._random_vocab, srv.LOG_PATH)

    srv.model = make_model()
    srv.client = make_client()
    srv._random_vocab = ["孤独", "霧", "光"]
    srv.tagger = make_tagger([
        make_word("夕暮れ", "名詞"),
        make_word("港", "名詞"),
        make_word("船", "名詞"),
        make_word("の", "助詞"),
        make_word("錆", "名詞"),
        make_word("静か", "形容詞"),
    ])
    srv.LOG_PATH = str(tmp_path / "test.log")

    with TestClient(srv.app) as tc:
        yield tc

    srv.model, srv.client, srv.tagger, srv._random_vocab, srv.LOG_PATH = orig


# ── TONE_MAP / build_tone_line ────────────────────────────────────────────────

ALL_AXES = ["brightness", "quietness", "mystery", "warmth", "era",
            "scale", "density", "decay", "mood", "color",
            "lighting", "spatial", "clarity"]

class TestToneMap:
    def test_all_axes_present(self):
        for axis in ALL_AXES:
            assert axis in TONE_MAP, f"{axis} が TONE_MAP にない"

    def test_each_axis_has_level3(self):
        for axis in ALL_AXES:
            assert -3 in TONE_MAP[axis], f"{axis}: -3 がない"
            assert  3 in TONE_MAP[axis], f"{axis}: +3 がない"

    def test_each_axis_has_all_nonzero_levels(self):
        for axis in ALL_AXES:
            for v in [-3, -2, -1, 1, 2, 3]:
                assert v in TONE_MAP[axis], f"{axis}: {v} がない"

    def test_zero_not_in_any_axis(self):
        for axis in ALL_AXES:
            assert 0 not in TONE_MAP[axis], f"{axis}: 0 が誤って登録されている"

    def test_build_tone_line_empty_when_all_zero(self):
        tone = {axis: 0 for axis in ALL_AXES}
        assert build_tone_line(tone) == ""

    def test_build_tone_line_empty_dict(self):
        assert build_tone_line({}) == ""

    def test_build_tone_line_unknown_axis_ignored(self):
        result = build_tone_line({"nonexistent_axis": 2})
        assert result == ""

    def test_build_tone_line_includes_phrase(self):
        for axis in ALL_AXES:
            line = build_tone_line({axis: 1})
            assert TONE_MAP[axis][1] in line

    def test_build_tone_line_level3_positive(self):
        for axis in ALL_AXES:
            line = build_tone_line({axis: 3})
            assert TONE_MAP[axis][3] in line

    def test_build_tone_line_level3_negative(self):
        for axis in ALL_AXES:
            line = build_tone_line({axis: -3})
            assert TONE_MAP[axis][-3] in line

    def test_build_tone_line_multiple_axes(self):
        tone = {"scale": 3, "decay": -3, "mood": 2}
        line = build_tone_line(tone)
        assert TONE_MAP["scale"][3] in line
        assert TONE_MAP["decay"][-3] in line
        assert TONE_MAP["mood"][2] in line

    def test_build_tone_line_prefix(self):
        line = build_tone_line({"brightness": 1})
        assert line.startswith("- Tone / atmosphere:")

    @pytest.mark.parametrize("axis", ["scale", "density", "decay", "mood", "color",
                                       "lighting", "spatial", "clarity"])
    def test_new_axes_individually(self, axis):
        for v in [-3, -2, -1, 1, 2, 3]:
            line = build_tone_line({axis: v})
            assert TONE_MAP[axis][v] in line

    def test_out_of_range_value_ignored(self):
        # ±4 以上は TONE_MAP にないので無視されて空文字列になる
        assert build_tone_line({"brightness": 4}) == ""
        assert build_tone_line({"brightness": -4}) == ""

    def test_all_values_are_nonempty_strings(self):
        for axis, levels in TONE_MAP.items():
            for v, phrase in levels.items():
                assert isinstance(phrase, str) and phrase, f"{axis}[{v}] が空または文字列でない"


# ── _INSTRUCTIONS / pick_instruction ─────────────────────────────────────────

class TestPickInstruction:
    MODES = ["near", "far", "combo", "journey"]

    def test_all_modes_present(self):
        for mode in self.MODES:
            assert mode in _INSTRUCTIONS

    def test_each_mode_has_multiple_variants(self):
        for mode in self.MODES:
            assert len(_INSTRUCTIONS[mode]) >= 2, f"{mode} のバリアントが1種類しかない"

    def test_near_contains_pivot_and_near(self):
        result = pick_instruction("near", pivot="孤独", near="静寂, 霧")
        assert "孤独" in result and "静寂" in result

    def test_far_contains_pivot_and_far(self):
        result = pick_instruction("far", pivot="孤独", far="賑わい, 祭り")
        assert "孤独" in result and "賑わい" in result

    def test_combo_contains_pivot_near_far(self):
        result = pick_instruction("combo", pivot="孤独", near="静寂", far="賑わい")
        assert "孤独" in result and "静寂" in result and "賑わい" in result

    def test_journey_contains_start_end_path(self):
        result = pick_instruction("journey", start="孤独", end="光", path="孤独 → 静寂 → 光")
        assert "孤独" in result and "光" in result

    def test_returns_different_variants(self):
        results = {pick_instruction("near", pivot="孤独", near="静寂") for _ in range(30)}
        assert len(results) > 1, "30回試行して1種類しか出なかった"


# ── /random ───────────────────────────────────────────────────────────────────

class TestRandom:
    def test_returns_word(self, client):
        res = client.get("/random")
        assert res.status_code == 200
        assert res.json()["word"] in ["孤独", "霧", "光"]


# ── /similar ──────────────────────────────────────────────────────────────────

class TestSimilar:
    def test_known_word_returns_results(self, client):
        res = client.get("/similar?word=孤独&topn=3")
        assert res.status_code == 200
        data = res.json()
        assert "results" in data
        assert len(data["results"]) <= 3

    def test_unknown_word_returns_error(self, client):
        res = client.get("/similar?word=未登録単語&topn=3")
        assert res.status_code == 200
        assert "error" in res.json()

    def test_topn_respected(self, client):
        res = client.get("/similar?word=孤独&topn=2")
        assert res.status_code == 200
        assert len(res.json()["results"]) <= 2


# ── /distant ──────────────────────────────────────────────────────────────────

class TestDistant:
    def test_known_word_returns_results(self, client):
        res = client.get("/distant?word=孤独&topn=3")
        assert res.status_code == 200
        assert "results" in res.json()

    def test_unknown_word_returns_error(self, client):
        res = client.get("/distant?word=未登録&topn=3")
        assert res.status_code == 200
        assert "error" in res.json()

    def test_topn_respected(self, client):
        res = client.get("/distant?word=孤独&topn=2")
        assert res.status_code == 200
        assert len(res.json()["results"]) <= 2


# ── /similarity ───────────────────────────────────────────────────────────────

class TestSimilarity:
    def test_returns_score(self, client):
        res = client.get("/similarity?word1=霧&word2=煙")
        assert res.status_code == 200
        data = res.json()
        assert "score" in data
        assert isinstance(data["score"], float)

    def test_unknown_word1_error(self, client):
        res = client.get("/similarity?word1=未登録&word2=霧")
        assert res.status_code == 200
        assert "error" in res.json()

    def test_unknown_word2_error(self, client):
        res = client.get("/similarity?word1=霧&word2=未登録")
        assert res.status_code == 200
        assert "error" in res.json()

    def test_both_words_unknown_error(self, client):
        res = client.get("/similarity?word1=未登録A&word2=未登録B")
        assert res.status_code == 200
        assert "error" in res.json()

    def test_score_is_float(self, client):
        res = client.get("/similarity?word1=霧&word2=煙")
        assert isinstance(res.json()["score"], float)


# ── /prompt ───────────────────────────────────────────────────────────────────

class TestPrompt:
    BASE = {"pivot": "孤独", "near": ["静寂"], "far": ["賑わい"]}

    def test_mode_near(self, client):
        res = client.post("/prompt", json={**self.BASE, "mode": "near"})
        assert res.status_code == 200
        data = res.json()
        assert "prompt" in data and "scene_ja" in data

    def test_mode_far(self, client):
        res = client.post("/prompt", json={**self.BASE, "mode": "far"})
        assert res.status_code == 200
        data = res.json()
        assert "prompt" in data and "scene_ja" in data

    def test_mode_combo(self, client):
        res = client.post("/prompt", json={**self.BASE, "mode": "combo"})
        assert res.status_code == 200
        data = res.json()
        assert "prompt" in data and "scene_ja" in data

    def test_mode_journey(self, client):
        res = client.post("/prompt", json={
            **self.BASE, "mode": "journey",
            "path": ["孤独", "静寂", "光"],
        })
        assert res.status_code == 200
        assert "prompt" in res.json()

    def test_journey_without_path_returns_error(self, client):
        res = client.post("/prompt", json={**self.BASE, "mode": "journey", "path": []})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_unknown_mode_returns_error(self, client):
        res = client.post("/prompt", json={**self.BASE, "mode": "invalid"})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_style_passed_to_claude(self, client):
        srv.client = make_client()
        client.post("/prompt", json={**self.BASE, "mode": "near", "style": "水彩画"})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "水彩画" in content

    def test_keywords_passed_to_claude(self, client):
        srv.client = make_client()
        client.post("/prompt", json={**self.BASE, "mode": "near", "keywords": ["月", "廃墟"]})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "月" in content and "廃墟" in content

    def test_claude_api_error_returns_error(self, client):
        srv.client.messages.create.side_effect = Exception("API down")
        res = client.post("/prompt", json={**self.BASE, "mode": "near"})
        assert res.status_code == 200
        assert "error" in res.json()
        srv.client.messages.create.side_effect = None

    def test_response_parses_scene_and_prompt(self, client):
        srv.client = make_client(scene="テスト情景", prompt_text="test, prompt")
        res = client.post("/prompt", json={**self.BASE, "mode": "combo"})
        data = res.json()
        assert data["scene_ja"] == "テスト情景"
        assert data["prompt"] == "test, prompt"

    def test_malformed_claude_response_falls_back(self, client):
        msg = MagicMock()
        msg.content = [MagicMock(text="no prefix at all")]
        srv.client.messages.create.return_value = msg
        res = client.post("/prompt", json={**self.BASE, "mode": "near"})
        assert res.status_code == 200
        assert "prompt" in res.json()

    def test_tone_included_in_claude_call(self, client):
        srv.client = make_client()
        client.post("/prompt", json={**self.BASE, "mode": "combo", "tone": {"brightness": -2, "mystery": 2}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert TONE_MAP["brightness"][-2] in content
        assert TONE_MAP["mystery"][2] in content

    def test_zero_tone_not_in_claude_call(self, client):
        srv.client = make_client()
        client.post("/prompt", json={**self.BASE, "mode": "combo", "tone": {"brightness": 0}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Tone / atmosphere" not in content

    def test_out_of_range_tone_ignored_in_prompt(self, client):
        srv.client = make_client()
        client.post("/prompt", json={**self.BASE, "mode": "combo", "tone": {"brightness": 4}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Tone / atmosphere" not in content

    @pytest.mark.parametrize("axis", ["scale", "density", "decay", "mood", "color",
                                       "lighting", "spatial", "clarity"])
    def test_new_tone_axes_in_prompt(self, client, axis):
        srv.client = make_client()
        client.post("/prompt", json={**self.BASE, "mode": "combo", "tone": {axis: 2}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert TONE_MAP[axis][2] in content

    def test_tone_level3_in_prompt(self, client):
        srv.client = make_client()
        client.post("/prompt", json={**self.BASE, "mode": "combo",
                                     "tone": {"brightness": 3, "decay": -3}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert TONE_MAP["brightness"][3] in content
        assert TONE_MAP["decay"][-3] in content

    def test_all_new_axes_in_single_prompt(self, client):
        srv.client = make_client()
        tone = {"scale": 1, "density": -1, "decay": 2, "mood": -2, "color": 3,
                "lighting": 2, "spatial": -1, "clarity": 1}
        client.post("/prompt", json={**self.BASE, "mode": "combo", "tone": tone})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        for axis, val in tone.items():
            assert TONE_MAP[axis][val] in content

    @pytest.mark.parametrize("axis,val", [
        ("lighting", -3), ("lighting", 3),
        ("spatial",  -3), ("spatial",  3),
        ("clarity",  -3), ("clarity",  3),
    ])
    def test_new_axes_level3_in_prompt(self, client, axis, val):
        srv.client = make_client()
        client.post("/prompt", json={**self.BASE, "mode": "combo", "tone": {axis: val}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert TONE_MAP[axis][val] in content


# ── /arithmetic ───────────────────────────────────────────────────────────────

class TestArithmetic:
    def test_positive_only(self, client):
        res = client.post("/arithmetic", json={"positive": ["霧", "光"]})
        assert res.status_code == 200
        assert "results" in res.json()

    def test_negative_only(self, client):
        res = client.post("/arithmetic", json={"negative": ["静寂"]})
        assert res.status_code == 200
        assert "results" in res.json()

    def test_positive_and_negative(self, client):
        res = client.post("/arithmetic", json={"positive": ["霧"], "negative": ["光"]})
        assert res.status_code == 200
        assert "results" in res.json()

    def test_empty_input_returns_error(self, client):
        res = client.post("/arithmetic", json={})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_unknown_word_returns_error(self, client):
        res = client.post("/arithmetic", json={"positive": ["未登録"]})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_unknown_negative_word_returns_error(self, client):
        res = client.post("/arithmetic", json={"negative": ["未登録"]})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_input_words_excluded_from_results(self, client):
        srv.model.most_similar.return_value = [("霧", 0.99), ("光", 0.8), ("煙", 0.7)]
        res = client.post("/arithmetic", json={"positive": ["霧"], "negative": ["光"]})
        words = [w for w, _ in res.json()["results"]]
        assert "霧" not in words
        assert "光" not in words

    def test_topn_respected(self, client):
        srv.model.most_similar.return_value = [(f"w{i}", 0.9 - i * 0.01) for i in range(20)]
        res = client.post("/arithmetic", json={"positive": ["光"], "topn": 3})
        assert len(res.json()["results"]) <= 3


# ── /cluster ─────────────────────────────────────────────────────────────────

class TestCluster:
    def test_returns_results(self, client):
        res = client.post("/cluster", json={"words": ["霧", "静寂"]})
        assert res.status_code == 200
        assert "results" in res.json()

    def test_input_words_excluded(self, client):
        srv.model.most_similar.return_value = [("霧", 0.9), ("煙", 0.8), ("静寂", 0.7)]
        res = client.post("/cluster", json={"words": ["霧", "静寂"]})
        words = [w for w, _ in res.json()["results"]]
        assert "霧" not in words
        assert "静寂" not in words

    def test_single_word_returns_error(self, client):
        res = client.post("/cluster", json={"words": ["霧"]})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_empty_words_returns_error(self, client):
        res = client.post("/cluster", json={"words": []})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_unknown_word_returns_error(self, client):
        res = client.post("/cluster", json={"words": ["霧", "未登録"]})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_topn_respected(self, client):
        srv.model.most_similar.return_value = [(f"w{i}", 0.9 - i * 0.01) for i in range(20)]
        res = client.post("/cluster", json={"words": ["霧", "静寂"], "topn": 3})
        assert len(res.json()["results"]) <= 3


# ── /journey ──────────────────────────────────────────────────────────────────

class TestJourney:
    def test_basic_path(self, client):
        res = client.post("/journey", json={"start": "孤独", "end": "光", "steps": 2})
        assert res.status_code == 200
        data = res.json()
        assert "path" in data
        assert data["path"][0] == "孤独"
        assert data["path"][-1] == "光"

    def test_path_length(self, client):
        res = client.post("/journey", json={"start": "孤独", "end": "光", "steps": 3})
        assert res.status_code == 200
        assert len(res.json()["path"]) >= 2

    def test_same_start_end_returns_error(self, client):
        res = client.post("/journey", json={"start": "孤独", "end": "孤独"})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_unknown_start_returns_error(self, client):
        res = client.post("/journey", json={"start": "未登録", "end": "光"})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_unknown_end_returns_error(self, client):
        res = client.post("/journey", json={"start": "孤独", "end": "未登録"})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_default_steps(self, client):
        res = client.post("/journey", json={"start": "孤独", "end": "光"})
        assert res.status_code == 200
        assert "path" in res.json()

    def test_steps_zero_returns_start_and_end(self, client):
        res = client.post("/journey", json={"start": "孤独", "end": "光", "steps": 0})
        assert res.status_code == 200
        data = res.json()
        assert "path" in data
        assert data["path"][0] == "孤独"
        assert data["path"][-1] == "光"

    def test_path_has_no_duplicates(self, client):
        res = client.post("/journey", json={"start": "孤独", "end": "光", "steps": 3})
        path = res.json()["path"]
        assert len(path) == len(set(path))


# ── /analyze ──────────────────────────────────────────────────────────────────

class TestAnalyze:
    def test_extracts_nouns_adjectives_verbs(self, client):
        res = client.post("/analyze", json={"text": "夕暮れの港に静かな船"})
        assert res.status_code == 200
        words = res.json()["words"]
        assert isinstance(words, list)
        assert "の" not in words   # 助詞は除外
        assert "錆" not in words   # 1文字は除外

    def test_returns_unique_words(self, client):
        srv.tagger = make_tagger([make_word("霧", "名詞"), make_word("霧", "名詞")])
        res = client.post("/analyze", json={"text": "霧霧"})
        assert res.json()["words"].count("霧") <= 1

    def test_empty_text_returns_empty_list(self, client):
        srv.tagger = make_tagger([])
        res = client.post("/analyze", json={"text": ""})
        assert res.status_code == 200
        assert res.json()["words"] == []

    def test_verb_is_extracted(self, client):
        srv.tagger = make_tagger([make_word("走る", "動詞")])
        res = client.post("/analyze", json={"text": "走る"})
        assert "走る" in res.json()["words"]

    def test_all_filtered_returns_empty(self, client):
        srv.tagger = make_tagger([
            make_word("は", "助詞"),
            make_word("a", "名詞"),   # 1文字
        ])
        res = client.post("/analyze", json={"text": "は a"})
        assert res.json()["words"] == []


# ── /expand ───────────────────────────────────────────────────────────────────

class TestExpand:
    def test_basic_expand(self, client):
        res = client.post("/expand", json={"text": "夕暮れの港に錆びた船"})
        assert res.status_code == 200
        data = res.json()
        assert "words" in data
        assert "word_map" in data
        assert "prompt" in data
        assert "scene_ja" in data

    def test_word_map_keys_match_words(self, client):
        res = client.post("/expand", json={"text": "夕暮れの港に錆びた船"})
        data = res.json()
        assert set(data["word_map"].keys()) == set(data["words"])

    def test_no_extractable_words_returns_error(self, client):
        srv.tagger = make_tagger([make_word("の", "助詞")])
        res = client.post("/expand", json={"text": "の"})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_style_and_keywords_passed(self, client):
        srv.client = make_client()
        client.post("/expand", json={"text": "夕暮れの港", "style": "油絵", "keywords": ["夕焼け"]})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "油絵" in content
        assert "夕焼け" in content

    def test_max_6_words_extracted(self, client):
        srv.tagger = make_tagger([make_word(f"単語{i}", "名詞") for i in range(7)])
        srv.model.__contains__ = lambda self, w: True
        res = client.post("/expand", json={"text": "test"})
        if "words" in res.json():
            assert len(res.json()["words"]) <= 6

    def test_claude_error_returns_error(self, client):
        srv.client.messages.create.side_effect = Exception("API down")
        res = client.post("/expand", json={"text": "夕暮れの港に錆びた船"})
        assert res.status_code == 200
        assert "error" in res.json()
        srv.client.messages.create.side_effect = None

    def test_tone_included_in_expand_call(self, client):
        srv.client = make_client()
        client.post("/expand", json={"text": "夕暮れの港に錆びた船", "tone": {"warmth": -1, "quietness": 2}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert TONE_MAP["warmth"][-1] in content
        assert TONE_MAP["quietness"][2] in content

    def test_zero_tone_not_in_expand_call(self, client):
        srv.client = make_client()
        client.post("/expand", json={"text": "夕暮れの港に錆びた船", "tone": {"brightness": 0}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "Tone / atmosphere" not in content

    @pytest.mark.parametrize("axis", ["scale", "density", "decay", "mood", "color",
                                       "lighting", "spatial", "clarity"])
    def test_new_tone_axes_in_expand(self, client, axis):
        srv.client = make_client()
        client.post("/expand", json={"text": "夕暮れの港に錆びた船", "tone": {axis: -2}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert TONE_MAP[axis][-2] in content

    def test_tone_level3_in_expand(self, client):
        srv.client = make_client()
        client.post("/expand", json={"text": "夕暮れの港に錆びた船",
                                     "tone": {"scale": 3, "mood": -3}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert TONE_MAP["scale"][3] in content
        assert TONE_MAP["mood"][-3] in content

    @pytest.mark.parametrize("axis,val", [
        ("lighting", -3), ("lighting", 3),
        ("spatial",  -3), ("spatial",  3),
        ("clarity",  -3), ("clarity",  3),
    ])
    def test_new_axes_level3_in_expand(self, client, axis, val):
        srv.client = make_client()
        client.post("/expand", json={"text": "夕暮れの港に錆びた船", "tone": {axis: val}})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert TONE_MAP[axis][val] in content

    def test_all_new_axes_in_single_expand(self, client):
        srv.client = make_client()
        tone = {"lighting": -2, "spatial": 3, "clarity": -1}
        client.post("/expand", json={"text": "夕暮れの港に錆びた船", "tone": tone})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        for axis, val in tone.items():
            assert TONE_MAP[axis][val] in content

    def test_response_parses_scene_ja(self, client):
        srv.client = make_client(scene="港の夕景", prompt_text="harbor, dusk")
        res = client.post("/expand", json={"text": "夕暮れの港に錆びた船"})
        data = res.json()
        assert data["scene_ja"] == "港の夕景"
        assert data["prompt"] == "harbor, dusk"

    def test_topn_affects_word_map_size(self, client):
        srv.model.most_similar.return_value = [("霧", 0.9), ("煙", 0.8), ("光", 0.7)]
        res = client.post("/expand", json={"text": "夕暮れの港に錆びた船", "topn": 2})
        data = res.json()
        for neighbors in data["word_map"].values():
            assert len(neighbors) <= 2

    def test_duplicate_words_deduplicated(self, client):
        srv.tagger = make_tagger([
            make_word("夕暮れ", "名詞"),
            make_word("夕暮れ", "名詞"),
            make_word("港", "名詞"),
        ])
        res = client.post("/expand", json={"text": "夕暮れ夕暮れ港"})
        data = res.json()
        assert data["words"].count("夕暮れ") == 1


# ── /evaluate ─────────────────────────────────────────────────────────────────

class TestEvaluate:
    VALID_PROMPT = "a foggy harbor at dusk, muted tones, melancholic atmosphere, soft diffused light"

    def test_basic_success(self, client):
        srv.client = make_eval_client()
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        assert res.status_code == 200
        data = res.json()
        assert "score" in data
        assert "dimensions" in data
        assert "suggestions" in data

    def test_score_parsed_correctly(self, client):
        srv.client = make_eval_client(score=72)
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        assert res.json()["score"] == 72

    def test_score_boundary_zero(self, client):
        srv.client = make_eval_client(score=0)
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        assert res.json()["score"] == 0

    def test_score_boundary_hundred(self, client):
        srv.client = make_eval_client(score=100)
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        assert res.json()["score"] == 100

    def test_dimensions_has_all_keys(self, client):
        srv.client = make_eval_client()
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        dims = res.json()["dimensions"]
        for key in ["subject", "composition", "lighting", "mood", "detail"]:
            assert key in dims, f"dimensions に '{key}' がない"

    def test_dimension_values_parsed_correctly(self, client):
        srv.client = make_eval_client(subject=8, composition=6, lighting=7, mood=9, detail=5)
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        dims = res.json()["dimensions"]
        assert dims["subject"] == 8
        assert dims["composition"] == 6
        assert dims["lighting"] == 7
        assert dims["mood"] == 9
        assert dims["detail"] == 5

    def test_suggestions_is_list(self, client):
        srv.client = make_eval_client()
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        assert isinstance(res.json()["suggestions"], list)

    def test_suggestions_count(self, client):
        srv.client = make_eval_client(suggestions=["提案A", "提案B", "提案C"])
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        assert len(res.json()["suggestions"]) == 3

    def test_suggestions_content_preserved(self, client):
        suggestions = ["光源を指定しましょう", "前景を追加しましょう", "色温度を明示しましょう"]
        srv.client = make_eval_client(suggestions=suggestions)
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        assert res.json()["suggestions"] == suggestions

    def test_short_prompt_returns_error(self, client):
        res = client.post("/evaluate", json={"prompt": "short"})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_empty_prompt_returns_error(self, client):
        res = client.post("/evaluate", json={"prompt": ""})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_whitespace_only_prompt_returns_error(self, client):
        res = client.post("/evaluate", json={"prompt": "   "})
        assert res.status_code == 200
        assert "error" in res.json()

    def test_prompt_included_in_claude_call(self, client):
        srv.client = make_eval_client()
        client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert self.VALID_PROMPT in content

    def test_scene_ja_included_in_claude_call_when_provided(self, client):
        srv.client = make_eval_client()
        client.post("/evaluate", json={"prompt": self.VALID_PROMPT, "scene_ja": "霧の港の夕景"})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        assert "霧の港の夕景" in content

    def test_scene_ja_optional(self, client):
        srv.client = make_eval_client()
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        assert res.status_code == 200
        assert "error" not in res.json()

    def test_scene_ja_absent_when_not_provided(self, client):
        srv.client = make_eval_client()
        client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        content = srv.client.messages.create.call_args.kwargs["messages"][0]["content"]
        # scene_ja が省略されたとき Japanese scene description セクションは含まれない
        assert "Japanese scene description" not in content

    def test_claude_api_error_returns_error(self, client):
        srv.client.messages.create.side_effect = Exception("API down")
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        assert res.status_code == 200
        assert "error" in res.json()
        srv.client.messages.create.side_effect = None

    def test_malformed_response_returns_default_structure(self, client):
        msg = MagicMock()
        msg.content = [MagicMock(text="some random text without expected format")]
        srv.client.messages.create.return_value = msg
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        assert res.status_code == 200
        data = res.json()
        # エラーにはならず、デフォルト値（score=0）が返る
        assert "score" in data
        assert data["score"] == 0

    def test_partial_response_parsed(self, client):
        msg = MagicMock()
        msg.content = [MagicMock(text="SCORE: 55\nSUBJECT: 6\nSUGGESTIONS:\n・色彩を豊かに")]
        srv.client.messages.create.return_value = msg
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        data = res.json()
        assert data["score"] == 55
        assert data["dimensions"].get("subject") == 6
        assert len(data["suggestions"]) == 1

    def test_suggestions_strip_bullet(self, client):
        suggestions = ["光源を指定して"]
        srv.client = make_eval_client(suggestions=suggestions)
        res = client.post("/evaluate", json={"prompt": self.VALID_PROMPT})
        # ・ プレフィックスが除去されていること
        for s in res.json()["suggestions"]:
            assert not s.startswith("・")


# ── /history ──────────────────────────────────────────────────────────────────

SAMPLE_ENTRY_PROMPT = {
    "timestamp": "2026-04-12T10:00:00+00:00",
    "endpoint": "/prompt",
    "params": {"pivot": "孤独", "near": ["静寂"], "far": ["賑わい"], "mode": "combo",
               "style": "", "keywords": [], "path": [], "tone": {}},
    "scene_ja": "霧の中に佇む孤独な情景",
    "prompt": "foggy harbor, dusk, muted tones",
}
SAMPLE_ENTRY_EXPAND = {
    "timestamp": "2026-04-12T11:00:00+00:00",
    "endpoint": "/expand",
    "params": {"text": "夕暮れの港", "style": "", "keywords": [], "topn": 5, "tone": {}},
    "scene_ja": "夕暮れに染まる港の情景",
    "prompt": "sunset harbor, warm tones, sailing boat",
}


@pytest.fixture()
def history_client(client):
    """client フィクスチャを流用し、ログファイルパスも一緒に返す。"""
    yield client, Path(srv.LOG_PATH)


def write_log_entries(log_file: Path, *entries) -> None:
    """テスト用ログファイルにエントリを書き込む。"""
    log_file.write_text(
        "".join(_json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
        encoding="utf-8",
    )


class TestHistory:
    def test_no_log_file_returns_empty(self, history_client):
        tc, _ = history_client
        res = tc.get("/history")
        assert res.status_code == 200
        data = res.json()
        assert data["entries"] == []
        assert data["total"] == 0

    def test_returns_entries_newest_first(self, history_client):
        tc, log_file = history_client
        write_log_entries(log_file, SAMPLE_ENTRY_PROMPT, SAMPLE_ENTRY_EXPAND)
        res = tc.get("/history")
        assert res.status_code == 200
        entries = res.json()["entries"]
        # 後に書いた EXPAND が先頭に来る（新着順）
        assert entries[0]["endpoint"] == "/expand"
        assert entries[1]["endpoint"] == "/prompt"

    def test_total_reflects_all_matches(self, history_client):
        tc, log_file = history_client
        write_log_entries(log_file, SAMPLE_ENTRY_PROMPT, SAMPLE_ENTRY_EXPAND)
        assert tc.get("/history").json()["total"] == 2

    def test_search_filters_by_scene_ja(self, history_client):
        tc, log_file = history_client
        write_log_entries(log_file, SAMPLE_ENTRY_PROMPT, SAMPLE_ENTRY_EXPAND)
        data = tc.get("/history?q=孤独").json()
        assert data["total"] == 1
        assert data["entries"][0]["endpoint"] == "/prompt"

    def test_search_filters_by_prompt(self, history_client):
        tc, log_file = history_client
        write_log_entries(log_file, SAMPLE_ENTRY_PROMPT, SAMPLE_ENTRY_EXPAND)
        data = tc.get("/history?q=sailing").json()
        assert data["total"] == 1
        assert data["entries"][0]["endpoint"] == "/expand"

    def test_search_no_match_returns_empty(self, history_client):
        tc, log_file = history_client
        write_log_entries(log_file, SAMPLE_ENTRY_PROMPT)
        data = tc.get("/history?q=一致しない文字列XYZ").json()
        assert data["entries"] == []
        assert data["total"] == 0

    def test_limit_respected(self, history_client):
        tc, log_file = history_client
        write_log_entries(log_file, *[
            {**SAMPLE_ENTRY_PROMPT, "timestamp": f"2026-04-12T10:{i:02d}:00+00:00"}
            for i in range(5)
        ])
        res = tc.get("/history?limit=3").json()
        assert len(res["entries"]) == 3
        assert res["total"] == 5

    def test_offset_skips_entries(self, history_client):
        tc, log_file = history_client
        write_log_entries(log_file, *[
            {**SAMPLE_ENTRY_PROMPT, "timestamp": f"2026-04-12T10:{i:02d}:00+00:00"}
            for i in range(5)
        ])
        assert len(tc.get("/history?limit=10&offset=3").json()["entries"]) == 2

    def test_malformed_lines_skipped(self, history_client):
        tc, log_file = history_client
        log_file.write_text(
            "not json\n" +
            _json.dumps(SAMPLE_ENTRY_PROMPT, ensure_ascii=False) + "\n\n",
            encoding="utf-8",
        )
        assert tc.get("/history").json()["total"] == 1
