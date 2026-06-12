"""
Mock DB session for eval suite.

Replaces models.base.sync_session_factory with an in-memory mock.
The mock session supports:
  session.execute(text(...), {...}) -> MockResult
  session.commit() -> no-op
  session.rollback() -> no-op

Pre-configured to return fake voice, customer context, and avatar payloads.
"""

from contextlib import contextmanager
from typing import Any

_FAKE_VOICE_PAYLOAD = {
    "tonalitaet": {
        "grundton": "direkt",
        "signalwoerter": ["Test", "Signal"],
    },
    "grundton": "direkt",
    "satzarchitektur": "kurze Saetze, klare Struktur",
    "signalwoerter": ["Test", "Signal"],
    "fuellwoerter": [],
    "verbotene_woerter": [],
    "intensitaetsmarker": ["immer", "nie", "klar"],
    "erzaehlmuster": "story-first",
    "emotionaler_ausdruck": "verhalten",
    "persoenlichkeits_stance": "authentisch",
    "emotionaler_subtext": "motivierend",
    "ueberzeugungsstil": "evidenzbasiert",
    "zielgruppen_sprachfilter": "Mittelstand",
    "vermeidungsprofil": ["Buzzwords", "KI-Signale"],
    "referenz_saetze": ["Das ist ein Beispielsatz."],
    "sprache_der_zielgruppe": "direkt und pragmatisch",
    "content_trigger": ["Schmerz", "Wunsch"],
}

_FAKE_CONTEXT_PAYLOAD = {
    "person": {"name": "Eval Test", "branche": "Beratung"},
    "angebot": {"leistung": "Coaching", "zielgruppe": "Unternehmer"},
    "positionierung": "Experte fuer Klarheit",
    "kernbotschaft": "Klarheit vor Strategie",
    "expertise": ["Fuehrung", "Strategie"],
    "unternehmensgeschichte": "Zehn Jahre Unternehmenserfahrung.",
    "zielgruppe": "Unternehmer im Mittelstand",
    "werte": ["Ehrlichkeit", "Wirksamkeit"],
    "wunschzustand": None,
    "innenwelt": None,
}

_FAKE_AVATAR_PAYLOAD = {
    "identitaet": {"alter": "35-55", "rolle": "Unternehmer"},
    "content_trigger": ["Klarheit", "Wachstum"],
    "sprache_der_zielgruppe": "direkt und pragmatisch",
}


class MockRow:
    """Simulates a SQLAlchemy row with .payload attribute."""

    def __init__(self, payload: dict):
        self.payload = payload

    def __getitem__(self, idx):
        if idx == 0:
            return self.payload
        raise IndexError(idx)


class MockResult:
    def __init__(self, rows: list):
        self._rows = rows

    def fetchone(self) -> MockRow | None:
        if self._rows:
            return self._rows[0]
        return None

    def fetchall(self) -> list:
        return self._rows

    def scalar(self) -> Any:
        if self._rows:
            row = self._rows[0]
            if hasattr(row, "__iter__"):
                try:
                    return next(iter(row))
                except StopIteration:
                    return None
            return row
        return 0


class MockSession:
    """In-memory mock session. Responds to the SQL patterns used by p01/p12/p12b tasks."""

    def __init__(self):
        self._execute_count = 0

    def execute(self, stmt, params=None) -> MockResult:
        self._execute_count += 1
        # Inspect the SQL string to return appropriate mock data
        stmt_text = str(stmt)

        if "tenant_voice_profile" in stmt_text:
            return MockResult([MockRow(_FAKE_VOICE_PAYLOAD)])

        if "tenant_customer_context" in stmt_text and "SELECT" in stmt_text.upper():
            # Version query returns scalar 0
            if "COALESCE" in stmt_text.upper() or "MAX" in stmt_text.upper():
                return MockResult([0])
            return MockResult([MockRow(_FAKE_CONTEXT_PAYLOAD)])

        if "tenant_audience_avatar" in stmt_text:
            return MockResult([MockRow(_FAKE_AVATAR_PAYLOAD)])

        # INSERT / UPDATE statements: return empty result
        return MockResult([])

    def commit(self):
        pass

    def rollback(self):
        pass


class MockSessionFactory:
    """Drop-in for models.base.sync_session_factory.

    Usage:
        factory = MockSessionFactory()
        with factory() as session:
            ...
    """

    def __call__(self):
        return self._context()

    @contextmanager
    def _context(self):
        yield MockSession()
