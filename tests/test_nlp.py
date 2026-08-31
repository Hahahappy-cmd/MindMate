from types import SimpleNamespace
import os

import pytest
import torch

from app.nlp.emotion_model import EmotionAnalyzer, EmotionModelError
from app.services import analysis


class FakeTokenizer:
    model_max_length = 8

    def encode(self, text, add_special_tokens=False):
        return list(range(len(text.split())))

    def num_special_tokens_to_add(self, pair=False):
        return 2

    def prepare_for_model(self, chunk, **_kwargs):
        return {"input_ids": [100, *chunk, 101], "attention_mask": [1] * (len(chunk) + 2)}

    def pad(self, chunks, padding=True, return_tensors="pt"):
        width = max(len(chunk["input_ids"]) for chunk in chunks)
        return {
            key: torch.tensor([values[key] + [0] * (width - len(values[key])) for values in chunks])
            for key in ("input_ids", "attention_mask")
        }


class FakeModel:
    config = SimpleNamespace(id2label={0: "JOY", 1: "SADNESS", 2: "OPTIMISM"})

    def __call__(self, input_ids, attention_mask):
        return SimpleNamespace(logits=torch.tensor([[2.0, -2.0, 0.5]] * input_ids.shape[0]))


class TieModel(FakeModel):
    def __call__(self, input_ids, attention_mask):
        return SimpleNamespace(logits=torch.tensor([[1.0, -2.0, 1.0]] * input_ids.shape[0]))


def fake_analyzer(**kwargs):
    analyzer = EmotionAnalyzer(max_length=8, overlap=2, **kwargs)
    analyzer._tokenizer = FakeTokenizer()
    analyzer._model = FakeModel()
    analyzer._torch = torch
    analyzer._device = torch.device("cpu")
    return analyzer


def test_multilabel_scores_and_metadata():
    result = fake_analyzer(threshold=0.6).analyze("one two three")
    assert list(result["emotions"]) == ["joy", "optimism"]
    assert result["dominant_emotion"] == "joy"
    assert result["score_semantics"] == "sigmoid_probability"


def test_long_text_is_chunked_and_no_label_falls_back_to_top():
    result = fake_analyzer(threshold=0.99).analyze(" ".join(["word"] * 15))
    assert result["chunks_analyzed"] > 1
    assert list(result["emotions"]) == ["joy"]


def test_empty_text_is_rejected():
    with pytest.raises(ValueError):
        fake_analyzer().analyze("")


def test_whitespace_only_text_is_rejected():
    with pytest.raises(ValueError):
        fake_analyzer().analyze("  \n")


def test_tied_top_labels_are_deterministic():
    analyzer = fake_analyzer(threshold=0.6)
    analyzer._model = TieModel()
    result = analyzer.analyze("ordinary journal entry")
    assert list(result["emotions"])[:2] == ["joy", "optimism"]
    assert result["dominant_emotion"] == "joy"


def test_keyword_fallback_is_explicit(monkeypatch):
    monkeypatch.setattr(analysis, "analyze_emotions", lambda _text: (_ for _ in ()).throw(EmotionModelError()))
    result = analysis.analyze_entry("I feel happy today")
    assert result["analysis_method"] == "keyword_fallback"
    assert result["emotion_score_semantics"] == "keyword_match_density"
    assert result["analysis_confidence"] is None


@pytest.mark.slow
@pytest.mark.skipif(os.getenv("RUN_SLOW_NLP_TESTS") != "1", reason="set RUN_SLOW_NLP_TESTS=1")
def test_real_model_smoke(monkeypatch):
    monkeypatch.undo()
    result = EmotionAnalyzer().analyze("I am grateful and happy that my friend helped me.")
    assert result["emotions"]
    assert 0 <= max(result["emotions"].values()) <= 1
