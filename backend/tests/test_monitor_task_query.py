# AUDITED-2026-08-19 (zubu-ci-gruen-machen): Tiefen-Audit, Datei vollstaendig gelesen.
"""Verhaltensnachweis: monitor_all_sources selektiert wirklich aktive Quellen.

Der statische Waechter in test_query_filter_invariants.py verbietet das Muster.
Dieser Test beweist die Wirkung am kompilierten SQL des echten Task-Pfads — ein
geloeschter oder verstuemmelter Filter wuerde den Waechter passieren, hier aber
auffallen.

Kein DB-Zugriff: die Session wird abgefangen, das Statement nur kompiliert.
"""

from unittest.mock import patch

from sqlalchemy.dialects import postgresql


class _CapturedResult:
    """Genug Oberflaeche, damit monitor_all_sources ohne Quellen sauber zurueckkehrt."""

    def scalars(self):
        return self

    def all(self):
        return []


class _CapturingSession:
    def __init__(self, statements):
        self._statements = statements

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, statement, *args, **kwargs):
        self._statements.append(statement)
        return _CapturedResult()


def _compiled_where_clause() -> str:
    """Fuehrt den echten Task aus und gibt die WHERE-Klausel seiner Query als SQL zurueck.

    Bewusst nur die WHERE-Klausel statt des gesamten Statements: das volle
    `compile()` loest `configure_mappers()` aus und konfiguriert damit JEDES je
    importierte Modell. In der Gesamtsuite scheitert das an einer unvollstaendigen
    Declarative-Registry (`relationship("Tenant")` in LLMProvider ohne geladenes
    Tenant-Modell) — ein vorbestehender Suite-Defekt, der diesen Test sonst blind
    machen wuerde: er stuerbe am Registry-Fehler, bevor er den Filter je pruefen kann.
    Die WHERE-Klausel ist ohnehin der einzige Testgegenstand.
    """
    from tasks import monitor_task

    statements: list = []
    with patch.object(monitor_task, "sync_session_factory", lambda: _CapturingSession(statements)):
        monitor_task.monitor_all_sources()

    assert statements, "monitor_all_sources hat keine Query abgesetzt"
    # RLS-Kontext (services/rls.py: set_rls_bypass_sync) setzt vor der eigentlichen
    # Query ein `SELECT set_config(...)` ab — ein reines TextClause ohne
    # `.whereclause`-Attribut. Das echte Select-Statement suchen, nicht auf
    # Index 0 vertrauen.
    select_statements = [s for s in statements if hasattr(s, "whereclause")]
    assert select_statements, f"Kein Statement mit WHERE-Klausel abgesetzt: {statements}"
    where_clause = select_statements[0].whereclause
    assert where_clause is not None, "Die Query hat gar keine WHERE-Klausel"
    return (
        str(
            where_clause.compile(
                dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
            )
        )
        .strip()
        .lower()
    )


def test_source_query_is_not_short_circuited_to_false() -> None:
    """Der eigentliche Live-Fehler: `Source.is_active is True` ergibt WHERE false."""
    where_clause = _compiled_where_clause()

    assert where_clause != "false", (
        "monitor_all_sources kompiliert zu WHERE false und selektiert damit dauerhaft "
        "null Quellen — die gesamte Quellen-Ueberwachung steht still."
    )


def test_source_query_actually_filters_on_is_active() -> None:
    """Gegenprobe: der Filter darf nicht ersatzlos entfallen sein.

    Geprueft wird nur die WHERE-Klausel. `is_active` steht ohnehin in der
    SELECT-Spaltenliste — eine Pruefung gegen das gesamte Statement waere auch dann
    gruen, wenn der Filter geloescht wuerde, und damit wertlos.
    """
    where_clause = _compiled_where_clause()

    assert "is_active" in where_clause, (
        f"Die WHERE-Klausel filtert nicht auf is_active — monitor_all_sources wuerde "
        f"auch inaktive Quellen pollen.\nWHERE: {where_clause}"
    )
