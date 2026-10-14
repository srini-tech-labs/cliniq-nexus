"""Patient-scoped hybrid retrieval: BM25 lexical ranking fused with embedding similarity.

The candidate pool is built only from rows already filtered to the selected patient.
Embeddings are precomputed per chunk at ingestion; only the question is embedded at
request time. If the embedding endpoint is unavailable, retrieval degrades to lexical.
"""
from __future__ import annotations

import math
import re
from collections import Counter

STOP = set("""a an and are as at be been but by can did do does for from had has have he her his how i if in into is it its
me my no not of on or our she so than that the their them then there these they this to was we were what when where which
who why will with you your patient patients record records documented document this any about after before during since
recent recently last latest""".split())
TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")


def normalize(text: str) -> str:
    return (text or "").replace("‑", "-").replace("‐", "-").replace("–", "-").replace("—", "-").lower()


def stem(tok: str) -> str:
    for suf in ("ations", "ation", "ings", "ing", "ies", "es", "ed", "s"):
        if len(tok) > len(suf) + 3 and tok.endswith(suf):
            return tok[: -len(suf)] + ("y" if suf == "ies" else "")
    return tok


def tokens(text: str) -> list[str]:
    return [stem(t) for t in TOKEN.findall(normalize(text)) if t not in STOP and len(t) > 1]


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.4, b: float = 0.75):
        self.docs = [Counter(tokens(d)) for d in docs]
        self.lens = [sum(d.values()) for d in self.docs]
        self.avg = sum(self.lens) / max(len(self.lens), 1)
        self.df = Counter(t for d in self.docs for t in d)
        self.n, self.k1, self.b = len(docs), k1, b

    def scores(self, query: str) -> list[float]:
        q = Counter(tokens(query))
        out = []
        for d, ln in zip(self.docs, self.lens):
            s = 0.0
            for t, qf in q.items():
                f = d.get(t)
                if not f:
                    continue
                idf = math.log(1 + (self.n - self.df[t] + 0.5) / (self.df[t] + 0.5))
                s += idf * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * ln / self.avg)) * qf
            out.append(s)
        return out


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def rank(question: str, candidates: list[dict], embeddings: dict[str, list[float]] | None,
         question_vec: list[float] | None, top_k: int = 8, recency: bool | str = False) -> tuple[list[dict], str]:
    """Reciprocal-rank fusion of BM25 and cosine similarity. Returns (ranked candidates, mode)."""
    if not candidates:
        return [], "none"
    lex = BM25([c["chunk_text"] for c in candidates]).scores(question)
    lex_rank = {i: r for r, i in enumerate(sorted(range(len(candidates)), key=lambda i: -lex[i])) if lex[i] > 0}
    sem_rank: dict[int, int] = {}
    mode = "lexical"
    if embeddings and question_vec:
        sims = [(i, cosine(question_vec, embeddings[c["chunk_id"]])) for i, c in enumerate(candidates) if c["chunk_id"] in embeddings]
        sims = [s for s in sims if s[1] > 0.35]
        sem_rank = {i: r for r, (i, _) in enumerate(sorted(sims, key=lambda s: -s[1]))}
        mode = "hybrid"
    k = 60.0
    fused = []
    for i, c in enumerate(candidates):
        score = 0.0
        if i in lex_rank:
            score += 1 / (k + lex_rank[i])
        if i in sem_rank:
            score += 1 / (k + sem_rank[i])
        if score:
            fused.append((score, i))
    if recency:  # True/"latest" boosts the newest sources; "earliest" boosts the oldest
        dated = sorted(range(len(candidates)), key=lambda i: candidates[i].get("source_date") or "", reverse=recency != "earliest")
        bonus = {i: 1 / (k + r) * 0.6 for r, i in enumerate(dated[:12])}
        fused = [(s + bonus.get(i, 0), i) for s, i in fused]
    fused.sort(key=lambda s: (-s[0], candidates[s[1]]["chunk_id"]))
    return [dict(candidates[i], score=round(s, 5)) for s, i in fused[:top_k]], mode
