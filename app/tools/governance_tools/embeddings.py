"""
Embeddings provider. Default: Voyage AI (Anthropic's recommended partner).

Why Voyage:
  - voyage-3-lite is $0.02 / 1M tokens (cheaper than OpenAI text-embedding-3-small)
  - 512 dimensions — smaller index, faster search, quality plenty for our KB size
  - Python SDK is minimal

  If retrieval quality looks weak at demo time, swap EMBEDDING_MODEL to
  "voyage-3" (1024-dim) and update schema.sql's vector() width to match,
  then re-seed.

To swap to OpenAI, replace embed_text with:
    from openai import OpenAI
    _openai = OpenAI()
    def embed_text(text, input_type="document"):
        resp = _openai.embeddings.create(
            model="text-embedding-3-small", input=text
        )
        return resp.data[0].embedding
And change the pgvector column to vector(1536) in schema.sql.
"""
import os
from functools import lru_cache
import voyageai

EMBEDDING_MODEL = "voyage-3-lite"
EMBEDDING_DIM = 512


@lru_cache(maxsize=1)
def _client() -> voyageai.Client:
    return voyageai.Client(api_key=os.environ["VOYAGE_API_KEY"])


def embed_text(text: str, input_type: str = "query") -> list[float]:
    """
    Embed a single string.

    input_type:
      - "query"    → use when embedding a user/agent search query (Voyage
                     optimizes the embedding for retrieval).
      - "document" → use when embedding KB chunks during seeding.
    """
    result = _client().embed(
        texts=[text], model=EMBEDDING_MODEL, input_type=input_type
    )
    return result.embeddings[0]


def embed_batch(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Embed many strings at once. Used during KB seeding."""
    # Voyage's free tier caps batch at 128, paid at 1000. We chunk defensively.
    out: list[list[float]] = []
    CHUNK = 128
    for i in range(0, len(texts), CHUNK):
        batch = texts[i : i + CHUNK]
        result = _client().embed(texts=batch, model=EMBEDDING_MODEL, input_type=input_type)
        out.extend(result.embeddings)
    return out
