"""Statische Invariante: kein Python-Identitaetsvergleich in SQLAlchemy-Filtern.

Hintergrund
-----------
`Source.is_active is True` ist ein Python-Identitaetsvergleich. `is` laesst sich
im Gegensatz zu `==` NICHT ueberladen, also erreicht der Ausdruck SQLAlchemy nie:
Python vergleicht die Identitaet des InstrumentedAttribute mit dem Singleton
`True`, das Ergebnis ist immer `False`, und SQLAlchemy uebersetzt dieses nackte
`False` klaglos zu `WHERE false`. Die Query liefert dauerhaft null Zeilen.

Das ist die gefaehrlichste Auspraegung dieser Fehlerklasse, weil sie als einzige
still ist: `not Source.is_active` oder `expr_a and expr_b` rufen `__bool__` auf und
werfen einen TypeError, `Source.is_active == True` erzeugt korrektes SQL. Nur
`is` / `is not` rutschen lautlos durch.

Warum ein AST-Scan und nicht ein Test pro Aufrufstelle
------------------------------------------------------
Eine pro Aufrufstelle durchgesetzte Regel leckt an der naechsten neu geschriebenen
Stelle. Dieser Test erzwingt die Invariante ueber den gesamten Backend-Quellbaum
und deckt damit auch Filter ab, die es heute noch nicht gibt.

Ruff faengt das nicht: E711/E712 greifen nur bei `==`/`!=`, und ein
SQLAlchemy-Plugin gibt es fuer Ruff nicht.
"""

import ast
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Aufrufe, deren Argumente als SQL-Ausdruecke ausgewertet werden. `filter_by`
# fehlt bewusst: es nimmt Keyword-Argumente, dort ist `is` syntaktisch unmoeglich.
SQL_PREDICATE_CALLS = frozenset({"where", "filter", "having", "and_", "or_", "not_"})

# Verzeichnisse ohne Produktionsqueries.
EXCLUDED_DIRS = frozenset({"tests", "alembic", "__pycache__", ".venv", "venv", "eval"})


def _iter_source_files() -> list[Path]:
    return sorted(
        path
        for path in BACKEND_ROOT.rglob("*.py")
        if not EXCLUDED_DIRS.intersection(path.relative_to(BACKEND_ROOT).parts)
    )


def _called_name(node: ast.Call) -> str | None:
    """Name der aufgerufenen Funktion — `sess.where(...)` und `and_(...)` gleichermassen."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _identity_comparisons(tree: ast.AST) -> list[ast.Compare]:
    """Jeder `is` / `is not`-Vergleich, der innerhalb eines SQL-Praedikats steht.

    Rekursiv, damit auch verschachtelte Faelle wie `where(or_(a, b is None))`
    gefunden werden. Instanz-Vergleiche ausserhalb von Filtern — etwa
    `if source.last_checked_at is None` — bleiben unangetastet und korrekt.
    """
    # Verschachtelte Praedikate wie `where(or_(...))` treffen denselben Vergleich
    # zweimal — einmal ueber `where`, einmal ueber `or_`. Position statt Objekt als
    # Schluessel, damit identische Ausdruecke in verschiedenen Zeilen erhalten bleiben.
    found: dict[tuple[int, int], ast.Compare] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _called_name(node) not in SQL_PREDICATE_CALLS:
            continue
        for argument in node.args:
            for inner in ast.walk(argument):
                if isinstance(inner, ast.Compare) and any(
                    isinstance(op, ast.Is | ast.IsNot) for op in inner.ops
                ):
                    found[(inner.lineno, inner.col_offset)] = inner
    return [found[key] for key in sorted(found)]


@pytest.mark.parametrize(
    "source_file", _iter_source_files(), ids=lambda p: str(p.relative_to(BACKEND_ROOT))
)
def test_no_identity_comparison_in_sql_predicates(source_file: Path) -> None:
    tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))

    offenders = _identity_comparisons(tree)

    assert not offenders, "\n".join(
        [
            f"{source_file.relative_to(BACKEND_ROOT)}: Python-Identitaetsvergleich im "
            f"SQL-Filter — kompiliert zu WHERE false, die Query liefert immer null Zeilen.",
            *(
                f"  Zeile {node.lineno}: {ast.unparse(node)}" f"   ->  {_suggested_fix(node)}"
                for node in offenders
            ),
        ]
    )


def _suggested_fix(node: ast.Compare) -> str:
    """Konkrete Ersetzung statt blossem 'ist falsch'."""
    left = ast.unparse(node.left)
    negated = isinstance(node.ops[0], ast.IsNot)
    right = ast.unparse(node.comparators[0])
    call = f"{left}.is_not({right})" if negated else f"{left}.is_({right})"
    return call


def test_scanner_flags_a_known_bad_pattern() -> None:
    """Der Waechter selbst braucht einen Nachweis, dass er ueberhaupt anschlaegt.

    Ohne diesen Test koennte der Scanner stillschweigend nichts finden — etwa weil
    sich die AST-Struktur aendert — und die Suite waere gruen aus dem falschen Grund.
    """
    bad = ast.parse("q = select(Source).where(Source.is_active is True)")

    offenders = _identity_comparisons(bad)

    assert len(offenders) == 1
    assert _suggested_fix(offenders[0]) == "Source.is_active.is_(True)"


def test_scanner_ignores_instance_comparisons_outside_filters() -> None:
    """`is None` an einer geladenen Instanz ist korrekt und darf nicht gemeldet werden.

    Genau dieses Muster steht in monitor_task.py direkt neben dem Fehler.
    """
    good = ast.parse("if source.last_checked_at is None:\n    pass")

    assert _identity_comparisons(good) == []


def test_scanner_finds_nested_identity_comparisons() -> None:
    """Verschachtelung darf den Scanner nicht abhaengen."""
    nested = ast.parse("q = select(X).where(or_(X.a == 1, X.tenant_id is None))")

    offenders = _identity_comparisons(nested)

    assert len(offenders) == 1
    assert _suggested_fix(offenders[0]) == "X.tenant_id.is_(None)"
