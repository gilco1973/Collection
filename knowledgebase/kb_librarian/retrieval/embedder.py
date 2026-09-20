"""Embedders: the protocol, the offline hash embedder and the HTTP embedder.

The bank chooses the provider by environment (principle 7 of the programme): with ``KB_EMBED_URL``
set, texts go to that endpoint (an on-premises one keeps them inside); without it the hash
embedder runs locally and nothing leaves the host.
"""

import hashlib
import math
import re
from typing import Protocol

import httpx

from kb_librarian.config import LibrarianSettings

BATCH_SIZE = 64
TIMEOUT_S = 30.0
_TOKEN = re.compile(r"\w+")


class EmbedError(RuntimeError):
    """The embedder could not produce vectors. The message names the failure, never the key or a text."""


class Embedder(Protocol):
    model_id: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Offline and deterministic: every ``\\w+`` token (lower-cased) is hashed into one of ``dim``
    buckets and the count vector is L2-normalised. Similarity is then token overlap — no synonyms,
    no meaning — which is enough to keep the suite and an air-gapped host working without a provider."""

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.model_id = f"hash-{dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        counts = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=4).digest()
            counts[int.from_bytes(digest, "big") % self.dim] += 1.0
        norm = math.sqrt(sum(c * c for c in counts))
        return [c / norm for c in counts] if norm else counts


def endpoint_tag(url: str) -> str:
    """Eight hex characters that identify an endpoint without naming it (the tag appears in doctor output)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]


class HttpEmbedder:
    """POSTs ``{"model", "input": [...]}`` in batches of ``BATCH_SIZE`` and reads ``data[i].embedding``
    (the shape OpenAI-compatible and Voyage-style endpoints share). ``dim`` is learnt from the first
    successful response. Every failure is an ``EmbedError`` that carries the failure type or status only.
    ``model_id`` is ``model@endpoint-tag``: the same model name behind another endpoint is another model,
    so a change of either makes ``doctor`` warn and the next build start over. One short-lived client
    per ``embed`` call: nothing to close, nothing leaks between chat turns."""

    def __init__(self, url: str, model: str, api_key: str | None, transport: httpx.BaseTransport | None = None):
        self.url = url
        self.model = model
        self.model_id = f"{model}@{endpoint_tag(url)}"
        self.dim = 0
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._transport = transport

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        with httpx.Client(timeout=TIMEOUT_S, transport=self._transport, headers=self._headers) as client:
            for start in range(0, len(texts), BATCH_SIZE):
                vectors.extend(self._post(client, texts[start : start + BATCH_SIZE]))
        return vectors

    def _post(self, client: httpx.Client, batch: list[str]) -> list[list[float]]:
        try:
            response = client.post(self.url, json={"model": self.model, "input": batch})
            response.raise_for_status()
            vectors = [[float(x) for x in item["embedding"]] for item in response.json()["data"]]
        except httpx.HTTPStatusError as exc:
            raise EmbedError(f"embedding endpoint returned {exc.response.status_code}") from None
        except httpx.HTTPError as exc:  # the type only: the message may carry the request
            raise EmbedError(f"embedding request failed ({type(exc).__name__})") from None
        except (KeyError, TypeError, ValueError):
            raise EmbedError("embedding response is not in the expected shape") from None
        if len(vectors) != len(batch) or not vectors[0] or any(len(v) != len(vectors[0]) for v in vectors):
            raise EmbedError("embedding response has the wrong number or size of vectors")
        self.dim = len(vectors[0])
        return vectors


def embedder_from_settings(settings: LibrarianSettings) -> Embedder:
    """The configured endpoint when ``KB_EMBED_URL`` is set, else the hash embedder of ``KB_EMBED_DIM``."""
    if settings.embed_url:
        key = settings.embed_api_key.get_secret_value() if settings.embed_api_key else None
        return HttpEmbedder(settings.embed_url, settings.embed_model, key)
    return HashEmbedder(settings.embed_dim)
