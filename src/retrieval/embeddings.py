import logging
from typing import Sequence

from src.config.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "BAAI/bge-small-en-v1.5"


class EmbeddingService:
    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        device: str | None = None,
        dimension: int | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device or settings.EMBEDDING_DEVICE
        self.dimension = dimension or settings.EMBEDDING_DIMENSION
        self._model = None

    @property
    def model(self):
        """Lazy load SentenceTransformer model."""
        if self._model is None:
            logger.info(
                "Loading embedding model '%s' on %s...",
                self.model_name,
                self.device,
            )
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
            )
        return self._model

    @property
    def max_tokens(self) -> int:
        """Longest input the model reads; anything after it is silently cut off."""
        return self.model.max_seq_length

    def token_count(self, text: str) -> int:
        """Number of tokens the model sees for `text`, including special tokens."""
        return len(self.model.tokenizer(text.strip(), add_special_tokens=True)["input_ids"])

    def embed_text(self, text: str) -> list[float]:
        """Generate a normalized 384-dim dense vector for a single string."""
        if not text or not text.strip():
            return [0.0] * self.dimension

        embedding = self.model.encode(
            text.strip(),
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return embedding.tolist()

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        """Generate normalized dense vectors for a batch of strings."""
        if not texts:
            return []

        cleaned = [t.strip() if t and t.strip() else "" for t in texts]
        embeddings = self.model.encode(
            cleaned,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return [vec.tolist() for vec in embeddings]


# Global singleton
embedding_service = EmbeddingService()
