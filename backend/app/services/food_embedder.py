"""Embed food names with Voyage AI, to find a food already in the calorie chart by meaning.

Uses the voyageai SDK directly, not langchain-voyageai: that wrapper loads a Hugging Face
tokenizer synchronously (a network call) for every text inside its async methods, sets no
timeout or retries, and embeds queries one per request.
"""

import logging
from collections.abc import Sequence
from typing import Literal

from voyageai.client_async import AsyncClient
from voyageai.error import VoyageError

from app.config import settings
from app.models.calorie_chart_item import EMBEDDING_DIMENSIONS

logger = logging.getLogger(__name__)

MODEL = "voyage-4"
TIMEOUT_SECONDS = 30.0
# Total attempts; the SDK retries rate limits, 503s and timeouts with backoff.
MAX_ATTEMPTS = 3


class EmbeddingError(Exception):
    """Voyage could not embed the texts (misconfiguration or API failure)."""


_client: AsyncClient | None = None


def _get_client() -> AsyncClient:
    global _client
    if _client is None:
        if not settings.voyage_api_key:
            raise EmbeddingError("VOYAGE_API_KEY is not configured")
        _client = AsyncClient(
            api_key=settings.voyage_api_key, max_retries=MAX_ATTEMPTS, timeout=TIMEOUT_SECONDS
        )
    return _client


async def close_client() -> None:
    # The SDK opens an HTTP session per request, so there is nothing to close.
    global _client
    _client = None


async def _embed(
    texts: Sequence[str], input_type: Literal["query", "document"]
) -> list[list[float]]:
    if not texts:
        return []
    try:
        result = await _get_client().embed(
            list(texts),
            model=MODEL,
            input_type=input_type,
            output_dimension=EMBEDDING_DIMENSIONS,
        )
    except VoyageError as e:
        raise EmbeddingError(type(e).__name__) from e
    if len(result.embeddings) != len(texts):
        raise EmbeddingError(f"Voyage returned {len(result.embeddings)} of {len(texts)} embeddings")
    logger.debug("Embedded %d %ss with %s", len(texts), input_type, MODEL)
    return result.embeddings


async def embed_queries(names: Sequence[str]) -> list[list[float]]:
    """Embed food names as said, to search the chart with. Raises EmbeddingError."""
    return await _embed(names, "query")


async def embed_documents(search_texts: Sequence[str]) -> list[list[float]]:
    """Embed chart foods' search texts, to be stored and searched. Raises EmbeddingError."""
    return await _embed(search_texts, "document")


# Fits CalorieChartItem.search_text.
MAX_SEARCH_TEXT_CHARS = 512


def search_text(food_item: str, aliases: Sequence[str]) -> str:
    """The text embedded for a chart food: its name, then its other names."""
    others = dict.fromkeys(" ".join(a.lower().split()) for a in aliases)
    others = [a for a in others if a and a != food_item]
    text = f"{food_item} | {', '.join(others)}" if others else food_item
    return text[:MAX_SEARCH_TEXT_CHARS]
