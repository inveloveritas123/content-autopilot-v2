"""Der Kostenwaechter — und die Frage, ob er ueberhaupt laeuft.

Bis zum 06.08.2026 fragte `_get_active_tenant_ids` nach `tenants.is_active`.
Die Spalte heisst `enabled`. Der erste Check warf, der zweite lief dadurch nie,
und der Task meldete stuendlich `{"status": "ok"}`. Beide Waechter waren tot,
und der Rueckgabewert sagte das Gegenteil.

⚠️ Die Messung laeuft in einem SUBPROZESS (Begruendung: `_subprozess_probe.py`).
Sowohl `tasks` als auch `sqlalchemy`/`models.base` werden von anderen
Testdateien gestubbt; `from tasks import cost_alert_task` scheitert dann mit
`ImportError: … (unknown location)`, und `Tenant.__table__` gaebe es gar nicht.
Der Spaltenabgleich braucht aber genau das echte Modell.
"""

from __future__ import annotations

import re

import pytest

from tests._subprozess_probe import fahre_probe

_PROBE = r"""
import json, re
import tasks.cost_alert_task as cat
import models.base
from models.tenant import Tenant

befund = {}

class _Ergebnis:
    def __init__(self, zeilen): self._z = zeilen
    def fetchall(self): return self._z

class _Session:
    def __init__(self, zeilen=()):
        self.sql = []
        self._z = list(zeilen)
    def execute(self, stmt, *a, **kw):
        self.sql.append(str(stmt))
        return _Ergebnis(self._z)

# --- Die Abfrage gegen das Modell -----------------------------------------
s = _Session(zeilen=[("a",), ("b",)])
befund["ids"] = cat._get_active_tenant_ids(s)
befund["sql"] = s.sql[0]
befund["spalten"] = sorted(Tenant.__table__.columns.keys())

# --- Rueckgabewert bei Fehler ---------------------------------------------
class _CtxWirft:
    def __enter__(self): raise RuntimeError("DB weg")
    def __exit__(self, *a): return False

class _CtxOk:
    def __enter__(self): return _Session()
    def __exit__(self, *a): return False

models.base.sync_session_factory = lambda: _CtxWirft()
befund["bei_fehler"] = cat.check_cost_alerts()

# --- Erfolg: BEIDE Waechter laufen ----------------------------------------
gelaufen = []
models.base.sync_session_factory = lambda: _CtxOk()
cat._check_cache_hit_rate = lambda s: gelaufen.append("cache")
cat._check_runaway = lambda s: gelaufen.append("runaway")
befund["bei_erfolg"] = cat.check_cost_alerts()
befund["gelaufen"] = list(gelaufen)

# --- Erster Wurf reisst den zweiten mit ------------------------------------
gelaufen2 = []
def _wirft(s): raise ValueError("kaputt")
cat._check_cache_hit_rate = _wirft
cat._check_runaway = lambda s: gelaufen2.append("runaway")
befund["bei_erstem_wurf"] = cat.check_cost_alerts()
befund["gelaufen2"] = list(gelaufen2)

print("BEFUND:" + json.dumps(befund))
"""

_SQL_SCHLUESSELWOERTER = {"true", "false", "and", "or", "not", "null", "where", "select", "from"}


@pytest.fixture(scope="module")
def befund() -> dict:
    return fahre_probe(_PROBE)


def test_abfrage_nennt_nur_spalten_die_es_wirklich_gibt(befund):
    """Jeder Bezeichner in der WHERE-Klausel muss eine Spalte von `tenants` sein.

    Gegen das MODELL geprueft, nicht gegen einen erwarteten Namen: `assert
    "enabled" in sql` haette den alten Fehler nur gefangen, wenn man den
    richtigen Namen ohnehin schon kannte. So faellt auch der naechste erfundene
    Spaltenname auf.
    """
    sql = befund["sql"]
    assert "tenants" in sql
    where = sql.split("WHERE", 1)[1]
    bezeichner = set(re.findall(r"[a-z_]{3,}", where)) - _SQL_SCHLUESSELWOERTER
    echte = set(befund["spalten"])

    assert bezeichner <= echte, (
        f"Abfrage nennt Spalten, die es nicht gibt: {sorted(bezeichner - echte)} "
        f"— vorhanden sind {sorted(echte)}"
    )


def test_is_active_existiert_nicht(befund):
    """Die Vorbedingung des Fehlers, damit der Test darueber nicht ins Leere prueft.

    Gaebe es die Spalte, waere die alte Abfrage korrekt gewesen und dieser
    ganze Testblock haette keinen Gegenstand.
    """
    assert "is_active" not in befund["spalten"]
    assert "is_active" not in befund["sql"]


def test_liefert_die_ids(befund):
    assert befund["ids"] == ["a", "b"]


def test_fehler_meldet_nicht_ok(befund):
    """Ein Waechter, der nichts geprueft hat, darf keinen Erfolg melden.

    Genau diese Zeile hat den Ausfall unsichtbar gemacht: der Beat-Zeitplan sah
    stuendlich `status: ok`, waehrend beide Pruefungen tot waren.
    """
    assert befund["bei_fehler"]["status"] == "error"
    assert befund["bei_fehler"]["reason"] == "alert_check_failed"
    assert befund["bei_fehler"]["exception"] == "RuntimeError"


def test_erfolg_meldet_ok_und_beide_waechter_laufen(befund):
    assert befund["bei_erfolg"]["status"] == "ok"
    assert befund["gelaufen"] == ["cache", "runaway"]


def test_erster_fehler_reisst_den_zweiten_waechter_mit(befund):
    """Der Grund, warum ein Spaltenname zwei Pruefungen gekostet hat.

    `_check_runaway` steht hinter `_check_cache_hit_rate` im selben try-Block —
    wirft der erste, laeuft der zweite nie. Das festzuhalten ist wichtiger als
    es umzubauen: wer die Struktur spaeter aendert, sieht hier, was daran hing.
    """
    assert befund["bei_erstem_wurf"]["status"] == "error"
    assert befund["gelaufen2"] == [], "der zweite Waechter laeuft nicht — genau darum ging es"


@pytest.mark.parametrize("feld", ["status", "checked_at"])
def test_rueckgabe_behaelt_ihre_felder(befund, feld):
    """Beide Ausgaenge tragen dieselben Schluessel — der Leser muss nicht raten."""
    assert feld in befund["bei_erfolg"]
    assert feld in befund["bei_fehler"]
