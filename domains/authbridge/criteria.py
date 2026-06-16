"""Medical-necessity criteria corpus + embeddings retrieval (the RAG path).

A small, synthetic library of evidence-based criteria (MCG/InterQual-style). The payer's
Clinical Guidelines agent retrieves the most relevant entry for a request via AI/ML
embeddings and cites it — grounding the review in real text, not a canned line.

Retrieval is best-effort: if embeddings are unavailable the caller falls back to a generic
guideline statement, so a run never breaks on it.
"""

from __future__ import annotations

import math

#: Synthetic criteria (illustrative, no proprietary content).
CRITERIA: list[dict[str, str]] = [
    {"id": "mri_lumbar", "text": (
        "Advanced imaging of the lumbar spine (MRI) is medically necessary when at least six "
        "weeks of conservative therapy (physical therapy, NSAIDs, activity modification) has "
        "failed and radicular symptoms persist, or when red-flag findings are present.")},
    {"id": "spine_red_flag", "text": (
        "Emergent spinal MRI is indicated without a conservative-care trial when red-flag signs "
        "of cauda equina syndrome or rapidly progressive neurologic deficit are present; this is "
        "a surgical emergency requiring an expedited determination.")},
    {"id": "step_therapy_biologic", "text": (
        "Specialty biologic drugs such as adalimumab (Humira) for rheumatoid arthritis, psoriasis "
        "or Crohn's disease require documented trial and failure (or intolerance/contraindication) "
        "of a preferred first-line agent — step therapy — before authorization, with the trial "
        "record attached.")},
    {"id": "mri_knee", "text": (
        "Knee MRI is medically necessary for suspected internal derangement (meniscal or "
        "ligamentous injury) after a failed course of conservative management and an inconclusive "
        "physical examination.")},
    {"id": "imaging_low_value", "text": (
        "Imaging is not medically necessary when the diagnosis does not match accepted indications "
        "for the requested study; such borderline requests warrant clinician (peer-to-peer) review "
        "rather than an automatic denial.")},
    {"id": "documentation", "text": (
        "A complete prior-authorization request must include a valid procedure code, at least one "
        "supporting diagnosis, the ordering provider's signature, and the documentation specified "
        "by the applicable medical-necessity policy.")},
]

#: Embedding cache keyed by the corpus signature (tuple of ids), so a DB-loaded corpus and the
#: built-in one are cached independently and re-embed only when the set of criteria changes.
_cache: dict[tuple[str, ...], list[tuple[dict[str, str], list[float]]]] = {}


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def retrieve(query: str, k: int = 1, corpus: list[dict[str, str]] | None = None) -> list[tuple[str, str, float]]:
    """Return the top-``k`` (id, text, score) criteria most similar to ``query`` via embeddings.

    ``corpus`` is a list of ``{"id", "text"}`` (the DB-backed criteria); defaults to the built-in
    ``CRITERIA`` when not supplied. The corpus is embedded once per signature (cached) + the query
    each call. Raises if embeddings are unavailable — callers treat retrieval as best-effort.
    """
    from engine.llm import embed

    items = corpus if corpus else CRITERIA
    key = tuple(c["id"] for c in items)
    if key not in _cache:
        _cache[key] = list(zip(items, embed([c["text"] for c in items])))
    qv = embed(query)[0]
    scored = sorted(((_cosine(qv, v), c) for c, v in _cache[key]), key=lambda t: -t[0])
    return [(c["id"], c["text"], score) for score, c in scored[:k]]
