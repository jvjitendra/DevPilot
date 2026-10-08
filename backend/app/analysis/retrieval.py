"""Hybrid retrieval boundary.

V1 keeps deterministic search and semantic/vector retrieval behind one interface,
so retrieval can evolve without changing the agent workflow.
"""
from dataclasses import dataclass

@dataclass
class RetrievedFile:
    path: str
    score: float
    source: str  # keyword | vector

class HybridRetriever:
    def search(self, query: str, limit: int = 8) -> list[RetrievedFile]:
        # Placeholder: GitHub tree/code search is wired in the next implementation step.
        return []
