from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
from typing import Any

from ..config import settings

logger = logging.getLogger(__name__)


class EmotionModelError(RuntimeError):
    """Raised when local transformer inference is unavailable."""


@dataclass(frozen=True)
class EmotionPrediction:
    dominant_emotion: str
    emotions: dict[str, float]
    model_name: str
    model_version: str
    analysis_method: str
    score_semantics: str
    threshold: float
    chunks_analyzed: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "dominant_emotion": self.dominant_emotion,
            "emotions": self.emotions,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "analysis_method": self.analysis_method,
            "score_semantics": self.score_semantics,
            "threshold": self.threshold,
            "chunks_analyzed": self.chunks_analyzed,
        }


class EmotionAnalyzer:
    """Lazy, reusable multi-label GoEmotions inference service."""

    def __init__(
        self,
        model_name: str = settings.emotion_model_name,
        model_version: str = settings.emotion_model_revision,
        threshold: float = settings.emotion_threshold,
        top_n: int = settings.emotion_top_n,
        max_length: int = settings.emotion_max_tokens,
        overlap: int = settings.emotion_chunk_overlap,
    ) -> None:
        if not 0 < threshold < 1:
            raise ValueError("Emotion threshold must be between 0 and 1")
        if top_n < 1:
            raise ValueError("Emotion top_n must be positive")
        self.model_name = model_name
        self.model_version = model_version
        self.threshold = threshold
        self.top_n = top_n
        self.max_length = max_length
        self.overlap = overlap
        self._tokenizer = None
        self._model = None
        self._torch = None
        self._device = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def _load(self) -> None:
        if self.is_loaded:
            return
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                revision=self.model_version,
            )
            model = AutoModelForSequenceClassification.from_pretrained(
                self.model_name,
                revision=self.model_version,
            )
            if torch.cuda.is_available():
                device = torch.device("cuda")
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                device = torch.device("mps")
            else:
                device = torch.device("cpu")
            model.to(device)
            model.eval()
            self._torch = torch
            self._tokenizer = tokenizer
            self._model = model
            self._device = device
            logger.info("Loaded emotion model %s on %s", self.model_name, device)
        except Exception as exc:
            logger.warning("Transformer emotion model unavailable: %s", type(exc).__name__)
            raise EmotionModelError("Transformer emotion model could not be loaded") from exc

    def _token_chunks(self, text: str) -> list[list[int]]:
        token_ids = self._tokenizer.encode(text, add_special_tokens=False)
        special_tokens = self._tokenizer.num_special_tokens_to_add(pair=False)
        payload_size = min(self.max_length, self._tokenizer.model_max_length) - special_tokens
        if payload_size <= 0:
            raise EmotionModelError("Tokenizer has no usable content window")
        overlap = min(self.overlap, payload_size - 1)
        step = payload_size - overlap
        return [token_ids[start:start + payload_size] for start in range(0, len(token_ids), step)] or [[]]

    @property
    def labels(self) -> list[str]:
        self._load()
        return [self._model.config.id2label[index].lower() for index in range(len(self._model.config.id2label))]

    def analyze(self, text: str) -> dict[str, Any]:
        if not text or not text.strip():
            raise ValueError("Emotion analysis requires non-empty text")
        self._load()
        chunks = self._token_chunks(text)
        encoded_chunks = [
            self._tokenizer.prepare_for_model(
                chunk,
                add_special_tokens=True,
                truncation=True,
                max_length=self.max_length,
                return_attention_mask=True,
            )
            for chunk in chunks
        ]
        batch = self._tokenizer.pad(encoded_chunks, padding=True, return_tensors="pt")
        batch = {name: tensor.to(self._device) for name, tensor in batch.items()}
        with self._torch.inference_mode():
            logits = self._model(**batch).logits
            probabilities = self._torch.sigmoid(logits).detach().cpu()

        weights = self._torch.tensor([max(1, len(chunk)) for chunk in chunks], dtype=probabilities.dtype)
        aggregate = (probabilities * weights.unsqueeze(1)).sum(dim=0) / weights.sum()
        id_to_label = {int(index): label.lower() for index, label in self._model.config.id2label.items()}
        ranked = sorted(
            ((id_to_label[index], float(score)) for index, score in enumerate(aggregate)),
            key=lambda item: (-item[1], item[0]),
        )
        selected = [item for item in ranked if item[1] >= self.threshold]
        if not selected:
            selected = ranked[:1]
        selected = selected[: self.top_n]
        prediction = EmotionPrediction(
            dominant_emotion=ranked[0][0],
            emotions={label: round(score, 6) for label, score in selected},
            model_name=self.model_name,
            model_version=self.model_version,
            analysis_method="transformer",
            score_semantics="sigmoid_probability",
            threshold=self.threshold,
            chunks_analyzed=len(chunks),
        )
        return prediction.as_dict()


@lru_cache(maxsize=1)
def get_emotion_analyzer() -> EmotionAnalyzer:
    return EmotionAnalyzer()


def analyze_emotions(text: str) -> dict[str, Any]:
    try:
        return get_emotion_analyzer().analyze(text)
    except (EmotionModelError, ValueError):
        raise
    except Exception as exc:
        logger.warning("Transformer emotion inference failed: %s", type(exc).__name__)
        raise EmotionModelError("Transformer emotion inference failed") from exc
