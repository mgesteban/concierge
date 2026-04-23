"""
Tool 1: search_governance_kb

RAG over the curated governance KB (Brown Act, Bagley-Keene, Robert's Rules,
BoardBreeze docs) stored in Supabase pgvector. Returns structured passages
WITH citations so the agent never has to hallucinate statute numbers.
"""
from typing import Any

from .db import get_supabase
from .embeddings import embed_text


def search_governance_kb(
    query: str,
    jurisdiction: str = "CA",
    top_k: int = 5,
) -> dict[str, Any]:
    """
    Semantic search over governance_kb.

    Returns:
        {
            "query": str,
            "results": [
                {
                    "content": str,       # the passage text
                    "source": str,        # e.g. "Gov. Code § 54954.2"
                    "document": str,      # e.g. "California Brown Act"
                    "section_title": str, # e.g. "Agenda posting requirements"
                    "jurisdiction": str,  # e.g. "CA"
                    "similarity": float,  # 0..1, higher = better match
                },
                ...
            ],
            "no_results": bool,  # true if nothing passed the similarity floor
        }
    """
    # Hard-cap top_k so a misbehaving agent can't blow up our context window.
    top_k = max(1, min(top_k, 10))

    # Embed the query (Voyage optimizes query-embeddings differently from docs).
    query_embedding = embed_text(query, input_type="query")

    # Call the Postgres RPC defined in db/schema.sql.
    # We pass jurisdiction='any' as NULL to skip filtering.
    supabase = get_supabase()
    jurisdiction_filter = None if jurisdiction == "any" else jurisdiction

    response = supabase.rpc(
        "match_governance_kb",
        {
            "query_embedding": query_embedding,
            "match_count": top_k,
            "jurisdiction_filter": jurisdiction_filter,
            # Similarity floor: passages below this are discarded.
            # 0.35 is generous; tune after seeding real data.
            "similarity_threshold": 0.35,
        },
    ).execute()

    results = response.data or []

    return {
        "query": query,
        "results": [
            {
                "content": row["content"],
                "source": row["source"],
                "document": row["document"],
                "section_title": row.get("section_title") or "",
                "jurisdiction": row["jurisdiction"],
                "similarity": round(float(row["similarity"]), 3),
            }
            for row in results
        ],
        "no_results": len(results) == 0,
    }
