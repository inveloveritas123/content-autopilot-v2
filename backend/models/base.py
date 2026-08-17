"""SQLAlchemy-Basis + Session-Factories.

Die DB-Engines werden LAZY beim ersten AUFRUF der Factory erzeugt, nicht beim Import.
Grund: Ein eager `create_async_engine(settings.database_url)` auf Modul-Ebene zwingt
jeden Importeur (inkl. reiner Unit-Tests ohne DB) zu einer gültigen DB-URL und lässt
sonst schon `from models.base import async_session_factory` mit einem kryptischen
Engine-Fehler crashen. Das war die Wurzel dafür, dass ~20 Testdateien `models.base`
mühsam stubben mussten.

`async_session_factory` / `sync_session_factory` sind aufrufbare Lazy-Proxys: der
Import bindet nur das Proxy-Objekt (DB-frei), erst der Aufruf `async_session_factory()`
baut Engine + echte sessionmaker-Factory (danach gecacht). Aufrufsemantik unverändert.
"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings


class Base(DeclarativeBase):
    pass


# Lazy-Singletons — erst beim ersten Zugriff gebaut, dann gecacht.
_async_engine = None
_async_session_factory = None
_sync_engine = None
_sync_session_factory = None


def _get_async_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(settings.database_url, echo=False)
    return _async_engine


def _get_async_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = sessionmaker(
            _get_async_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_factory


def _get_sync_engine():
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(settings.sync_database_url, echo=False)
        # ⛔ RLS-Wächter genau hier und nur hier: das ist die EINE Stelle, an
        # der jede Sync-Engine entsteht. Er repariert nichts — er macht
        # sichtbar, wenn eine Abfrage auf eine RLS-Tabelle ohne Tenant-Kontext
        # läuft und deshalb 0 Zeilen liefert (bzw. ein INSERT hart scheitert).
        # Ohne ihn ist dieser Zustand von einem korrekten Leerbefund nicht zu
        # unterscheiden — genau daran ist am 17.08.2026 der Telegram-Empfang
        # ausgefallen. Details: services/rls_guard.py.
        #
        # Fail-open beim Einhängen selbst: fehlt das Modul oder wirft es, darf
        # die Anwendung nicht starten-unfähig werden. Ein Wächter ist eine
        # Zusatzsicherung, keine Startbedingung.
        try:
            from services.rls_guard import aktiviere_rls_waechter

            aktiviere_rls_waechter(_sync_engine)
        except Exception:  # pragma: no cover
            pass
    return _sync_engine


def _get_sync_session_factory():
    global _sync_session_factory
    if _sync_session_factory is None:
        _sync_session_factory = sessionmaker(_get_sync_engine(), expire_on_commit=False)
    return _sync_session_factory


class _LazySessionFactory:
    """Aufrufbares Proxy: `factory()` baut/holt lazy die echte sessionmaker-Factory
    und ruft sie auf. Der Import des Proxys selbst berührt keine DB.
    Delegiert Attribut-Zugriffe (z.B. `.kw`, `.class_`) an die echte Factory."""

    __slots__ = ("_resolver",)

    def __init__(self, resolver):
        self._resolver = resolver

    def __call__(self, *args, **kwargs):
        return self._resolver()(*args, **kwargs)

    def __getattr__(self, item):
        # Nur echte sessionmaker-Attribute delegieren; interne _-Namen nicht auflösen.
        return getattr(self._resolver(), item)


async_session_factory = _LazySessionFactory(_get_async_session_factory)
sync_session_factory = _LazySessionFactory(_get_sync_session_factory)


# Engine-Attribute bleiben lazy per PEP 562 (selten direkt referenziert).
def __getattr__(name: str):
    if name == "async_engine":
        return _get_async_engine()
    if name == "sync_engine":
        return _get_sync_engine()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
