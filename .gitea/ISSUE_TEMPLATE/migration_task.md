---
name: Migration-Task
about: Issue das eine DB-Migration enthält
---

## Aufgabe
<!-- Beschreibung -->

## Migration-Checklist (Pflicht wenn Migration enthalten)
- [ ] Alembic-Migration geschrieben
- [ ] `scripts/safe_alembic.sh "upgrade head"` auf Live-DB ausgeführt
- [ ] `alembic current` zeigt `head`
- [ ] Container nach Code+Schema-Änderung neu gestartet
- [ ] Kein Datenverlust verifiziert

## Acceptance
<!-- Was muss funktionieren -->
