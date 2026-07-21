"""Tests für services/rag_rerank.py — Fokus auf rrf_fuse (rein arithmetisch,
DB-/LLM-frei, deterministisch testbar ohne Mocks).
"""

from __future__ import annotations

from services.rag_rerank import rrf_fuse


def test_rrf_fuse_boosts_ids_present_in_both_lists():
    """Ein Kandidat, der in BEIDEN Ranglisten auftaucht, akkumuliert Score aus
    beiden Rängen und muss vor einem Kandidaten landen, der nur in einer
    Liste (selbst auf Platz 1) vorkommt."""
    vector_ranked = ["only_vector", "both", "c"]
    lexical_ranked = ["both", "only_lexical", "d"]

    result = rrf_fuse(vector_ranked, lexical_ranked)

    assert result[0] == "both"
    assert set(result) == {"only_vector", "both", "c", "only_lexical", "d"}


def test_rrf_fuse_pure_vector_order_when_lexical_empty():
    """Ohne Lexical-Zweig entspricht die Fusion exakt der Vektor-Reihenfolge
    (Hybrid-Search muss bei leerem Lexical-Zweig auf reines Vektor-Retrieval
    zurückfallen, nicht crashen oder umsortieren)."""
    vector_ranked = ["a", "b", "c"]

    result = rrf_fuse(vector_ranked, [])

    assert result == ["a", "b", "c"]


def test_rrf_fuse_pure_lexical_order_when_vector_empty():
    """Symmetrischer Fall: leerer Vektor-Zweig ⇒ reine Lexical-Reihenfolge."""
    lexical_ranked = ["x", "y", "z"]

    result = rrf_fuse([], lexical_ranked)

    assert result == ["x", "y", "z"]


def test_rrf_fuse_both_empty_returns_empty():
    """Randfall: beide Listen leer ⇒ leeres Ergebnis, kein Fehler."""
    assert rrf_fuse([], []) == []


def test_rrf_fuse_respects_k_damping_constant():
    """Ein größeres k dämpft Rang-Unterschiede stärker — bei k=0 dominiert der
    Top-Rang jeder Liste fast vollständig (1/(0+1)=1.0 vs. 1/(0+2)=0.5), bei
    sehr großem k werden die Scores fast gleich (Kandidat mit zwei mittleren
    Rängen kann dann einen Top-1-Einzeltreffer überholen)."""
    vector_ranked = ["solo_top"]  # Rang 0 in vector, nirgends sonst
    lexical_ranked = ["b", "double_mid"]  # double_mid auf Rang 1

    # double_mid kommt nur lexikalisch vor (Rang 1) — mit Standard-k=60 reicht
    # ein einzelner Top-Treffer (solo_top, Rang 0 in vector) aus, um vorne zu
    # liegen, weil 1/(61) > 1/(62).
    result_default_k = rrf_fuse(vector_ranked, lexical_ranked, k=60)
    assert result_default_k[0] == "solo_top"

    # Bei k=0 ist der Unterschied zwischen Rang 0 und Rang 1 riesig
    # (1.0 vs. 0.5) — solo_top bleibt klar vorne.
    result_k0 = rrf_fuse(vector_ranked, lexical_ranked, k=0)
    assert result_k0[0] == "solo_top"
    assert result_k0[0] != "b"  # "b" liegt auf Rang 0 im Lexical-Zweig, aber vector fehlt


def test_rrf_fuse_stable_order_on_score_tie():
    """Bei exaktem Score-Gleichstand (z.B. je ein Solo-Treffer auf Rang 0 in
    getrennten Listen) muss die Reihenfolge deterministisch nach Erstauftreten
    sein (vector zuerst) — kein Nichtdeterminismus durch dict-Iteration."""
    vector_ranked = ["v0"]
    lexical_ranked = ["l0"]

    result = rrf_fuse(vector_ranked, lexical_ranked)

    # Beide haben denselben RRF-Score (1/(60+1)) — v0 zuerst, da im Vektor-Zweig
    # zuerst gesehen (stabile Sortierung nach Erstauftreten).
    assert result == ["v0", "l0"]
