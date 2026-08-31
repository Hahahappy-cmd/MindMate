from __future__ import annotations

from functools import lru_cache
import hashlib
import logging

import numpy as np

from ..config import settings

logger = logging.getLogger(__name__)


class ThemeModelError(RuntimeError):
    """Raised when semantic embedding inference is unavailable."""


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ThemeEmbedder:
    """Lazy MiniLM embedder with chunk-aware normalized mean pooling."""

    def __init__(self) -> None:
        self.model_name = settings.theme_model_name
        self.model_version = settings.theme_model_revision
        self.max_length = settings.theme_max_tokens
        self.overlap = settings.theme_chunk_overlap
        self._tokenizer = self._model = self._torch = self._device = None

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, revision=self.model_version)
            self._model = AutoModel.from_pretrained(self.model_name, revision=self.model_version)
            if torch.cuda.is_available():
                self._device = torch.device("cuda")
            elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
                self._device = torch.device("mps")
            else:
                self._device = torch.device("cpu")
            self._model.to(self._device).eval()
            self._torch = torch
        except Exception as exc:
            logger.warning("Theme embedding model unavailable: %s", type(exc).__name__)
            raise ThemeModelError("Theme embedding model could not be loaded") from exc

    def embed(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Theme embedding requires non-empty text")
        self._load()
        ids = self._tokenizer.encode(text, add_special_tokens=False)
        special = self._tokenizer.num_special_tokens_to_add(pair=False)
        payload = self.max_length - special
        step = payload - min(self.overlap, payload - 1)
        chunks = [ids[start:start + payload] for start in range(0, len(ids), step)] or [[]]
        encoded = [self._tokenizer.prepare_for_model(chunk, add_special_tokens=True, return_attention_mask=True) for chunk in chunks]
        batch = self._tokenizer.pad(encoded, padding=True, return_tensors="pt")
        batch = {key: value.to(self._device) for key, value in batch.items()}
        try:
            with self._torch.inference_mode():
                token_embeddings = self._model(**batch).last_hidden_state
                mask = batch["attention_mask"].unsqueeze(-1).expand(token_embeddings.size()).float()
                vectors = (token_embeddings * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
                vectors = self._torch.nn.functional.normalize(vectors, p=2, dim=1)
                weights = self._torch.tensor([max(1, len(chunk)) for chunk in chunks], device=self._device).float()
                vector = (vectors * weights.unsqueeze(1)).sum(0) / weights.sum()
                vector = self._torch.nn.functional.normalize(vector, p=2, dim=0)
            return np.round(vector.detach().cpu().numpy(), 7).tolist()
        except Exception as exc:
            logger.warning("Theme embedding inference failed: %s", type(exc).__name__)
            raise ThemeModelError("Theme embedding inference failed") from exc


@lru_cache(maxsize=1)
def get_theme_embedder() -> ThemeEmbedder:
    return ThemeEmbedder()
