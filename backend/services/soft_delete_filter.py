"""Der Soft-Delete-Filter fuer memory_chunks — eine Wahrheit statt vieler Kopien.

`deleted_at` markiert DSGVO-Art.-17-Loeschungen (api/data_deletion.py). Jede Zeile mit
gesetztem `deleted_at` befindet sich im 30-Tage-Recovery-Fenster und DARF in keinem
Lesepfad mehr auftauchen — nicht im RAG-Abruf, nicht in einer UI-Ansicht, nicht in einem
naechtlichen Scan. Anders als der Anweisungs-Filter (`services/anweisungs_marker.py`) hat
dieses Fragment KEINE Rohbestands-Ausnahme: Loeschung ist DSGVO-Pflicht, keine
Content-Qualitaetsfrage. Jeder Aufrufer bindet es unbedingt ein.

`deleted_at` ist fuer aktive Zeilen NULL, kein COALESCE noetig (anders als bei
`metadata->>'intent'`): `NULL IS NULL` ist in SQL eindeutig TRUE.

Grenze: das Fragment ist unqualifiziert. Bei einem Self-Join mit Alias
(z. B. `memory_chunks a JOIN memory_chunks b`) muss der Aufrufer die Spalte selbst
qualifizieren (`a.deleted_at IS NULL AND b.deleted_at IS NULL`).
"""

SQL_NICHT_GELOESCHT = "deleted_at IS NULL"
