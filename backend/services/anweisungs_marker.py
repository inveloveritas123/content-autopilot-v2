"""Ein Steuerungsmerkmal und sein Auswerter — bewusst in EINER Datei.

Eine Nachricht wie „Ich will einen neuen LinkedIn-Post machen" ist eine Anweisung, kein
Inhalt. `_versuche_gespraechsstart` markiert den zugehoerigen Memory-Chunk deshalb mit
`metadata.intent = "start_instruction"` (der Chunk selbst entsteht frueher —
`_store_chunk_async` laeuft vor allen Weichen, deshalb wird nachtraeglich markiert und
nicht vorher entschieden).

Warum Marker und Filter zusammen in einer Datei stehen: der Marker wurde am 05.08.2026
eingefuehrt und bis zum 06.08. von KEINER Stelle gelesen. Ein Etikett, dessen Auswerter
woanders wohnt, verliert seinen Auswerter — und niemand merkt es, weil beide Seiten fuer
sich genommen korrekt aussehen. Wer hier etwas aendert, sieht beide Haelften auf einmal.
"""

import json

#: Der Wert in `metadata->>'intent'` fuer Nachrichten, die ein Gespraech eroeffnet haben.
INTENT_START_INSTRUCTION = "start_instruction"

#: Das jsonb-Patch, mit dem `_markiere_chunk_als_anweisung` den Chunk markiert.
MARKER_PATCH_JSON = json.dumps({"intent": INTENT_START_INSTRUCTION})

#: WHERE-Praedikat, das markierte Chunks ausschliesst — OHNE fuehrendes `AND`, damit es
#: sich sowohl anhaengen als auch in eine Praedikatsliste einreihen laesst.
#:
#: `COALESCE` ist nicht kosmetisch: `metadata` ist nullable, und `NULL <> 'x'` ergibt in
#: SQL `NULL`, nicht `TRUE`. Ohne COALESCE fiele jeder Chunk ohne `metadata` stumm aus
#: jedem Ergebnis — aus dem Ausschluss weniger Chunks wuerde die Loeschung der meisten.
#:
#: Grenze des Fragments: `metadata` ist ein UNQUALIFIZIERTER Spaltenname. Das gilt nur
#: fuer Abfragen mit einem einzigen, nicht-aliasierten `memory_chunks` (der Normalfall
#: bei allen bisherigen Lesern). Bei einem Self-Join oder Alias (z. B. `memory_chunks a
#: JOIN memory_chunks b` wie in `api/memory_viz.py`) ist `metadata` mehrdeutig — dort
#: muss der Aufrufer die Spalte qualifizieren, bevor er dieses Praedikat einspleisst.
SQL_OHNE_ANWEISUNGEN = f"COALESCE(metadata->>'intent', '') <> '{INTENT_START_INSTRUCTION}'"
