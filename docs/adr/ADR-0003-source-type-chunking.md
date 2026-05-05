# ADR-0003: Source-Type-spezifische Chunking-Strategie

## Status

Akzeptiert (2026-05-04)

## Kontext

pgvector-Recall@20 (Anteil der 20 semantisch relevantesten Chunks die tatsaechlich in den Top-20-Ergebnissen erscheinen) war bei heterogenen Quellen unbefriedigend. Die Ursache: Ein universeller Chunker mit fixed max_tokens=600 behandelt alle Quell-Typen gleich (Issue #151).

Das fuehrt zu zwei entgegengesetzten Problemen:

1. **Zu grosse Chunks:** Lange YouTube-Transkripte (30-Minuten-Videos) werden in 600-Token-Bloecke zerschnitten, wobei semantische Einheiten zerrissen werden. Recall sinkt weil der relevante Kontext auf mehrere Chunks verteilt ist.
2. **Zu kleine Chunks:** Kurze Photo-OCR-Texte oder Voice-Notes (30 Sekunden) landen als Fragment-Chunks mit < 80 Token — zu wenig Kontext fuer sinnvolles Embedding. Drop-Logik fehlte voellig.

## Entscheidung

10 Source-Type-Konfigurationen werden eingefuehrt, jede mit eigenem `max_tokens`, `overlap` und `min_tokens` (Issue #151):

| Source-Type | max_tokens | overlap | min_tokens | Besonderheit |
|-------------|-----------|---------|-----------|-------------|
| youtube_transcript | 800 | 100 | 100 | Standard-Chunking |
| voice_note | - | - | - | Single-Chunk-Bypass (gesamte Note = 1 Chunk) |
| blog_post | 600 | 80 | 80 | Standard |
| newsletter | 600 | 80 | 80 | Standard |
| linkedin_post | 400 | 50 | 50 | Kurze Posts |
| photo_ocr | 300 | 30 | 40 | Kurze OCR-Texte |
| rss_article | 700 | 90 | 90 | Laengere Artikel |
| pdf_document | 800 | 100 | 100 | Technische Dokumente |
| web_scrape | 600 | 80 | 80 | Standard |
| manual_entry | 500 | 60 | 60 | Manuell eingegeben |

`drop_short_chunks=True`: Chunks unter `min_tokens` werden vor dem Embedding verworfen (kein Storage-Waste, kein Noise im Recall).

Voice-Note-Single-Chunk-Bypass: Eine Voice-Note unter 3 Min / 180s wird als ganzes Embedding gespeichert. Kein Zerrissen in Fragments.

## Konsequenzen

**Positiv:**
- Besserer Recall@20 ueber alle Source-Types (mesbar ueber `run_embedding_drift_monitor`)
- Kein Noise durch Fragment-Chunks unter `min_tokens`
- Voice-Notes als atomare Einheit aufrufbar

**Negativ:**
- Mehr Code-Wartungsaufwand wenn neue Source-Types hinzukommen: Config-Eintrag + Tests noetig
- Bestehende Embeddings muessen nicht sofort re-embedded werden, aber Recall-Verbesserung tritt erst nach Re-Embed ein

**Neutral:**
- Default-Werte (max_tokens=600, overlap=80, min=80) bleiben fuer unbekannte Types als Fallback erhalten (Constraint #6)

## Alternativen die verworfen wurden

**Universal-Chunker mit max_tokens=600 (Status quo):** Siehe Kontext — Photo-OCR-Texte zu kurz, YT-Transkripte zerrissen. Kein Weg dieses Problem mit einem einzigen Wert zu loesen.

**Semantisches Chunking via Embedding-Similarity:** Chunks werden erst getrennt wenn die cosine-Similarity zwischen benachbarten Saetzen unter einen Schwellwert faellt. Algorithmus korrekt aber teuer: jeder Chunking-Schritt benoetigt mehrere Embedding-Calls. Bei 1000 neuen Items/Tag wuerde das die API-Kosten signifikant erhoehen. Source-Type-Configs loesen 80% des Problems zu 0 Zusatzkosten.
