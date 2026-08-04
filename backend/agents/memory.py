"""Lightweight local-first memory & retrieval store for agents.

Uses pure Python + NumPy for local TF-IDF cosine similarity retrieval over:
- Resume bullet library (for Tailoring Agent)
- Past JD / score / outcome triples (for Fit Agent few-shot retrieval)
- Company research cache (to avoid redundant LLM calls)
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, Dict, List, Optional
import numpy as np


class AgentMemoryStore:
    def __init__(self) -> None:
        self.bullets: List[str] = []
        self.past_jobs: List[Dict[str, Any]] = []
        self.company_cache: Dict[str, str] = {}

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def _compute_vector(self, text: str, vocab: List[str]) -> np.ndarray:
        tokens = self._tokenize(text)
        counts = {}
        for t in tokens:
            counts[t] = counts.get(t, 0) + 1
        vec = np.zeros(len(vocab), dtype=float)
        for i, word in enumerate(vocab):
            vec[i] = counts.get(word, 0.0)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def add_resume_bullets(self, bullets: List[str]) -> None:
        for b in bullets:
            if b and b not in self.bullets:
                self.bullets.append(b)

    def query_resume_bullets(self, query: str, k: int = 5) -> List[str]:
        if not self.bullets:
            return []
        # Build vocabulary from bullets + query
        all_texts = self.bullets + [query]
        vocab = list(set(w for text in all_texts for w in self._tokenize(text)))
        if not vocab:
            return self.bullets[:k]

        q_vec = self._compute_vector(query, vocab)
        scored = []
        for b in self.bullets:
            b_vec = self._compute_vector(b, vocab)
            sim = float(np.dot(q_vec, b_vec))
            scored.append((sim, b))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [b for _, b in scored[:k]]

    def add_past_job(self, job_id: int, text: str, score: float, outcome: str) -> None:
        self.past_jobs.append({
            "job_id": job_id,
            "text": text,
            "score": score,
            "outcome": outcome,
        })

    def query_similar_jobs(self, query: str, k: int = 3) -> List[Dict[str, Any]]:
        if not self.past_jobs:
            return []
        all_texts = [j["text"] for j in self.past_jobs] + [query]
        vocab = list(set(w for text in all_texts for w in self._tokenize(text)))
        if not vocab:
            return self.past_jobs[:k]

        q_vec = self._compute_vector(query, vocab)
        scored = []
        for job in self.past_jobs:
            j_vec = self._compute_vector(job["text"], vocab)
            sim = float(np.dot(q_vec, j_vec))
            scored.append((sim, job))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [j for _, j in scored[:k]]

    def cache_company(self, company_name: str, summary: str) -> None:
        self.company_cache[company_name.lower().strip()] = summary

    def get_company(self, company_name: str) -> Optional[str]:
        return self.company_cache.get(company_name.lower().strip())


# Process-wide singleton instance
_memory_store: Optional[AgentMemoryStore] = None


def get_memory_store() -> AgentMemoryStore:
    global _memory_store
    if _memory_store is None:
        _memory_store = AgentMemoryStore()
    return _memory_store
