#!/usr/bin/env python3
"""G-RLS-KONTEXT: Statisches Gate gegen die RLS-Blindstellen-Klasse (2026-08-17).

Migration 058 aktivierte FORCE ROW LEVEL SECURITY auf 43 Tabellen. Jede
sync-DB-Session, die eine dieser Tabellen beruehrt, OHNE vorher den
Tenant-Kontext zu setzen (`set_rls_tenant_sync`/`set_rls_bypass_sync`), sieht
still 0 Zeilen statt eines Fehlers — der Vorfall, der zu 80 Fundstellen in
21 Dateien fuehrte (docs/RLS-FUNDLISTE-UEBERGABE.md).

Dieses Gate ist genau die Methode, mit der die Fundliste erzeugt wurde,
als dauerhafte Pruefung: fuer jeden `with sync_session_factory() as X:`-Block
in backend/tasks/ und backend/services/ wird per AST geprueft, ob eine
RLS-Tabelle referenziert wird, BEVOR im Block (bzw. nach einem `commit()`
erneut) ein `set_rls_tenant_sync`/`set_rls_bypass_sync`-Aufruf steht.

Bewusst NUR statisch (kein DB-Zugriff, keine Imports der gescannten Module):
das Gate muss auch laufen, wenn die DB nicht erreichbar ist, und es muss
schnell genug fuer jeden Push sein.

⛔ Was dieses Gate NICHT kann: erkennen, ob das URTEIL (TENANT vs. BYPASS)
fachlich richtig ist. Es prueft nur "wurde ueberhaupt einer der beiden
Aufrufe gemacht" — die inhaltliche Pruefung bleibt Aufgabe des Reviews
(genau wie beim Laufzeit-Waechter services/rls_guard.py, der das Gegenstueck
zur Laufzeit ist).

Exit-Code:
  0 — kein `with sync_session_factory()`-Block ohne RLS-Kontext gefunden.
  1 — mindestens ein Block referenziert eine RLS-Tabelle ohne vorherigen
      set_rls_*-Aufruf (Fundstellen-Liste auf stdout).

Nutzung:
    cd backend
    PYTHONPATH=. .venv/bin/python scripts/check_rls_context_gate.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

GATE_VERSION = "1.0.0"

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_SCAN_DIRS = ("tasks", "services")

#: Tabellen mit FORCE ROW LEVEL SECURITY (Migrationen 058, 061, 062).
#: Identisch zu services/rls_guard.py:RLS_TABELLEN — bewusst dupliziert statt
#: importiert, damit dieses Gate ohne Backend-Abhaengigkeiten (SQLAlchemy etc.)
#: laeuft. Aendert sich die Laufzeit-Liste, muss diese hier mitgezogen werden.
RLS_TABELLEN: frozenset[str] = frozenset(
    {
        "backtest_runs",
        "bot_session",
        "campaigns",
        "carousel_templates",
        "company_profile",
        "content_dna_profiles",
        "content_ideas",
        "content_performances",
        "content_pieces",
        "daily_cost_tenant",
        "deletion_requests",
        "dialogue_questions",
        "entrepreneur_answers",
        "hook_library",
        "idea_selection_logs",
        "idea_variants",
        "llm_call_logs",
        "llm_providers",
        "llm_trace",
        "memory_chunks",
        "profile_field_provenance",
        "projects",
        "quality_metrics",
        "research_findings",
        "scheduled_posts",
        "setup_pipeline_run",
        "source_items",
        "sources",
        "telegram_message_log",
        "tenant_audience_avatar",
        "tenant_bot_config",
        "tenant_branding",
        "tenant_concurrency",
        "tenant_customer_context",
        "tenant_customer_values",
        "tenant_reservoir",
        "tenant_review_queue",
        "tenant_telegram_link",
        "tenant_voice_profile",
        "throttle_events",
        "voice_drift_observation",
        "voice_feedback",
        "wizard_session",
    }
)

_RLS_SETTER_NAMES = {"set_rls_tenant_sync", "set_rls_bypass_sync"}
_COMMIT_NAMES = {"commit"}


def _call_name(node: ast.AST) -> str | None:
    """Name eines Funktions-/Methodenaufrufs, egal ob `f(...)` oder `x.f(...)`."""
    if not isinstance(node, ast.Call):
        return None
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


#: Nur String-Konstanten, die WIRKLICH SQL sind, duerfen einen Treffer ausloesen.
#: Ohne dieses Filter meldet das Gate auch `logger.error("... setup_pipeline_run ...")`
#: als "ungeschuetzten Zugriff" — ein reiner Log-Text ist aber keine Query.
_SQL_KEYWORDS = ("select ", "insert ", "update ", "delete ", " from ", " join ")


def _ist_sql_string(s: str) -> bool:
    low = f" {s.lower()} "
    return any(kw in low for kw in _SQL_KEYWORDS)


def _tabellen_in_strings(strings: list[str]) -> set[str]:
    hit = set()
    for s in strings:
        if not _ist_sql_string(s):
            continue
        low = s.lower()
        for t in RLS_TABELLEN:
            if t in low:
                hit.add(t)
    return hit


def _is_sync_session_with(item: ast.withitem, node: ast.With) -> bool:
    """Ist das ein `with sync_session_factory() as X:` (auch `async with`)?"""
    name = _call_name(item.context_expr)
    return name == "sync_session_factory"


class _BlockFinding:
    __slots__ = ("datei", "zeile", "tabellen")

    def __init__(self, datei: str, zeile: int, tabellen: set[str]):
        self.datei = datei
        self.zeile = zeile
        self.tabellen = tabellen


def _walk_in_order(node: ast.AST):
    """Wie ast.walk, aber in QUELLTEXT-/AUSFUEHRUNGSREIHENFOLGE (Pre-Order, DFS).

    ⛔ ast.walk() ist NICHT ausfuehrungsreihenfolge-treu — es ist eine
    Breitensuche ueber ast.iter_child_nodes(), die z.B. bei einem Try-Block
    den `commit()` im Except-Handler VOR einem tief verschachtelten
    SQL-String im try-Body liefern kann, obwohl der String im echten
    Programmablauf zuerst ausgefuehrt wird. Ein Kontext-Verfall-Gate, das
    sich auf Ausfuehrungsreihenfolge verlaesst (erst Query, dann commit()),
    braucht deshalb eine eigene Tiefensuche statt ast.walk().
    """
    yield node
    for child in ast.iter_child_nodes(node):
        yield from _walk_in_order(child)


def _scan_with_block(body: list[ast.stmt]) -> set[str]:
    """Prueft eine Liste von Statements (ein with-Block) auf ungeschuetzte RLS-Zugriffe.

    Ablauf-sensitiv in Ausfuehrungsreihenfolge (siehe _walk_in_order): sobald
    ein set_rls_*-Aufruf auftaucht, gilt der Kontext ab dort als gesetzt —
    bis zum naechsten `commit()` (SET LOCAL verfaellt dort, siehe
    rls_guard.py-Docstring), danach muss erneut gesetzt werden.

    Bewusst FLACH ueber verschachtelte if/try/for/with hinweg (ein
    State-Automat ueber den gesamten Block) statt eines State-Machines pro
    Zweig: ein False-Positive (Zweig A setzt, Zweig B nicht, Tool meldet
    trotzdem OK) waere ein STILLER Blindfleck — teurer als ein paar zu
    strenge Treffer, die im Review als harmlos erkannt werden.
    """
    kontext_gesetzt = False
    ungeschuetzt: set[str] = set()

    for stmt in body:
        for n in _walk_in_order(stmt):
            name = _call_name(n)
            if name in _RLS_SETTER_NAMES:
                kontext_gesetzt = True
                continue
            if name in _COMMIT_NAMES:
                kontext_gesetzt = False
                continue
            if not kontext_gesetzt and isinstance(n, ast.Constant) and isinstance(n.value, str):
                tabellen = _tabellen_in_strings([n.value])
                if tabellen:
                    ungeschuetzt |= tabellen
    return ungeschuetzt


def _scan_file(path: Path) -> list[_BlockFinding]:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError) as e:
        print(f"  WARNUNG: {path} konnte nicht geparst werden: {e}")
        return []

    findings: list[_BlockFinding] = []
    rel = path.relative_to(_BACKEND_ROOT)

    for node in ast.walk(tree):
        if not isinstance(node, ast.With | ast.AsyncWith):
            continue
        if not any(_is_sync_session_with(item, node) for item in node.items):
            continue
        ungeschuetzt = _scan_with_block(node.body)
        if ungeschuetzt:
            findings.append(_BlockFinding(str(rel), node.lineno, ungeschuetzt))

    return findings


def _evaluate() -> int:
    print(f"G-RLS-KONTEXT v{GATE_VERSION} — statisches Gate gegen RLS-Blindstellen")

    all_findings: list[_BlockFinding] = []
    scanned = 0
    for sub in _SCAN_DIRS:
        d = _BACKEND_ROOT / sub
        if not d.is_dir():
            continue
        for path in sorted(d.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            scanned += 1
            all_findings.extend(_scan_file(path))

    print(f"  {scanned} Datei(en) in {', '.join(_SCAN_DIRS)}/ gescannt.")

    if not all_findings:
        print("G-RLS-KONTEXT: OK — keine sync_session_factory()-Bloecke ohne RLS-Kontext.")
        return 0

    print(f"G-RLS-KONTEXT: {len(all_findings)} Fundstelle(n) ohne RLS-Kontext:")
    for f in sorted(all_findings, key=lambda f: (f.datei, f.zeile)):
        print(f"  - {f.datei}:{f.zeile} — Tabelle(n): {', '.join(sorted(f.tabellen))}")
    print(
        "REMEDIATION: direkt nach `with sync_session_factory() as X:` "
        "`set_rls_tenant_sync(X, tenant_id)` (Normalfall) oder "
        "`set_rls_bypass_sync(X, True)` PLUS Begruendungskommentar (Ausnahme, "
        "wenn der Block echt tenant-uebergreifend arbeitet) ergaenzen. "
        "Folgt im selben Block ein commit(), muss der Kontext DANACH erneut "
        "gesetzt werden (SET LOCAL verfaellt beim Commit) — siehe "
        "services/rls_guard.py und docs/RLS-FUNDLISTE-UEBERGABE.md."
    )
    return 1


def main() -> int:
    try:
        return _evaluate()
    except Exception as e:
        print(f"G-RLS-KONTEXT v{GATE_VERSION}: Gate konnte nicht laufen: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
