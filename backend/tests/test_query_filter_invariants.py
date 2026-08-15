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
import subprocess
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Praedikate in Methodenform: `query.where(...)`, `query.filter(...)`.
# `filter` steht NUR hier, niemals als freie Funktion — das gleichnamige Python-Builtin
# wird frei aufgerufen, und `filter(lambda x: x is not None, xs)` ist voellig korrekt.
# `filter_by` fehlt bewusst: es nimmt Keyword-Argumente, dort ist `is` syntaktisch unmoeglich.
PREDICATE_METHODS = frozenset({"where", "filter", "having"})

# Kombinatoren, die beide Schreibweisen kennen: `and_(...)` und `sa.and_(...)`.
PREDICATE_FUNCTIONS = frozenset({"and_", "or_", "not_"})

# Verzeichnisse ohne Produktionsqueries. Fremdcode steht hier NICHT drin: die Dateiliste
# kommt aus git, das kennt keine venvs.
EXCLUDED_DIRS = frozenset({"tests", "alembic", "eval"})


def _iter_source_files() -> list[Path]:
    """Alle versionierten Python-Dateien des Backends.

    Bewusst git statt `rglob` plus Verzeichnis-Blacklist: eine Blacklist leckt per
    Konstruktion. CI legt sein venv als `.ci-venv/` INNERHALB von backend/ an, womit der
    Scanner ueber yt_dlp, reportlab und google.auth lief und deren korrektes
    `filter(lambda x: x is not None, ...)` als Fehler meldete. Versionierte Dateien sind
    die exakte Definition von "unser Code": neue Projektverzeichnisse sind automatisch
    abgedeckt, Fremdcode ist es nie.

    `check=True` ist Absicht — fehlt git, soll der Test hart fehlschlagen statt still
    nichts zu scannen und gruen aus dem falschen Grund zu sein.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return sorted(
        BACKEND_ROOT / name
        for name in listing.stdout.split("\0")
        if name and not EXCLUDED_DIRS.intersection(Path(name).parts)
    )


def _is_predicate_call(node: ast.Call) -> bool:
    """Wird dieser Aufruf seine Argumente als SQL-Ausdruecke auswerten?"""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in PREDICATE_METHODS or func.attr in PREDICATE_FUNCTIONS
    if isinstance(func, ast.Name):
        return func.id in PREDICATE_FUNCTIONS
    return False


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
        if not isinstance(node, ast.Call) or not _is_predicate_call(node):
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


def test_scanner_ignores_builtin_filter() -> None:
    """`filter` ist auch ein Python-Builtin — dort ist `is not None` voellig korrekt.

    Das Builtin wird als freie Funktion aufgerufen, SQLAlchemys `filter` ausschliesslich
    als Methode. Ohne diese Unterscheidung meldet der Scanner gaengiges Python als Fehler:
    genau daran ist er in CI ueber yt_dlp, reportlab und google.auth gelaufen.
    """
    builtin_use = ast.parse("xs = list(filter(lambda x: x is not None, items))")

    assert _identity_comparisons(builtin_use) == []


def test_scanner_still_flags_query_filter_method() -> None:
    """Gegenprobe zum Builtin-Ausschluss: die Methodenform muss weiter anschlagen."""
    orm_use = ast.parse("q = session.query(X).filter(X.tenant_id is None)")

    offenders = _identity_comparisons(orm_use)

    assert len(offenders) == 1
    assert _suggested_fix(offenders[0]) == "X.tenant_id.is_(None)"


def test_scanner_covers_the_project_and_only_the_project() -> None:
    """Die Dateiliste stammt aus git — nicht aus einem Verzeichnis-Blacklist.

    Eine Blacklist von venv-Namen leckt per Konstruktion: CI legt sein venv als
    `.ci-venv/` INNERHALB von backend/ an, womit der Scanner ueber Third-Party-Pakete
    lief. Versionierte Dateien sind die exakte Definition von "unser Code" — neue
    Projektverzeichnisse sind automatisch abgedeckt, Fremdcode nie.
    """
    files = {str(path.relative_to(BACKEND_ROOT)) for path in _iter_source_files()}

    # Nicht leer und nicht zufaellig richtig: die Datei mit dem schwersten Fund muss dabei sein.
    assert "tasks/monitor_task.py" in files
    assert len(files) > 50, f"Nur {len(files)} Dateien — die Auswahl greift zu kurz"
    assert not [
        f for f in files if "site-packages" in f or "venv" in f
    ], "Fremdcode in der Dateiliste — der Scanner meldet fremde Builtin-Aufrufe als Fehler"
