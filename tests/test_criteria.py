"""Tests for the medical-necessity criteria corpus + cosine (the RAG retrieval math).
Offline: the embeddings call (`retrieve`) needs a key, so only the pure parts are unit-tested."""

from domains.authbridge.criteria import CRITERIA, _cosine


def test_corpus_is_non_empty_and_well_formed():
    assert len(CRITERIA) >= 5
    assert all(c["id"] and c["text"] for c in CRITERIA)


def test_cosine_identity_and_orthogonality():
    assert _cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert abs(_cosine([1.0, 0.0], [0.0, 1.0])) < 1e-9
    assert _cosine([], []) == 0.0  # guarded against zero-length
