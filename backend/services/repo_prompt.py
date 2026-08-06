"""Prompts, die im Repo leben — nicht in content-truth.

## Warum es beide Orte gibt

`content-truth/` ist die Ablage fuer Prompts, die ohne Deploy aenderbar sein
sollen: der `LayeredStorageAdapter` liest ein beschreibbares Overlay
(`/app/data/prompts-custom`) vor der read-only Base. Wer diesen Weg nutzt,
registriert seinen Prompt in `prompt_loader.PROMPT_PATHS`.

Manche Prompts gehoeren aber zum Code und nicht in die Ablage: sie enthalten
Platzhalter, die genau eine Aufrufstelle fuellt, und eine Aenderung ohne
passende Code-Aenderung waere ein Fehler, kein Feature. Fuer die ist diese
Datei zustaendig.

## Warum das aufgeschrieben werden musste (06.08.2026)

Beide P08-Prompts existierten gleichzeitig, und die Kette log es an:

* `content-truth/prompts/P08-fragen-konversation.md` — 18.694 Bytes, Stand
  12.06.2026, verlangt `{name} {branche} {standort} {teamgroesse}
  {du_oder_sie} {signalwoerter}`. Keiner dieser Platzhalter existiert im Code,
  also warf die Platzhalter-Probe **bei jedem Aufruf** `KeyError: 'name'`.
* `backend/prompts/P08_conversation.md` — 2.587 Bytes, Stand 04.08.2026, der
  Gespraechs-Umbau. Das ist der Prompt, der tatsaechlich lief.

Der Ort, der „Source of Truth" hiess, trug einen zwei Monate alten Prompt, der
sich strukturell nicht laden liess. Der Ort, der „Fallback" hiess, trug die
Wahrheit. Wer P08 in content-truth verbesserte, aenderte nichts — und die
Meldung darueber kam einmal pro Prozess und ging als Rauschen durch.

**Die Lehre:** Ein Rueckfall, der dauerhaft greift, IST die Quelle. Dann muss
er so heissen. Eine Kette `A → B → C` sagt von sich aus nie, auf welcher Stufe
sie gerade steht.

Muster uebernommen von `services.p14_entry_service._load_p14_prompt`, das
denselben Weg schon ging.
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

#: backend/prompts/ — relativ zu dieser Datei, damit es im Container
#: (/app/prompts) und im Repo gleichermassen aufgeht.
_PROMPT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "prompts"))

#: Einmal laut je Datei (ERROR, Sentry-Schwelle) statt bei jedem Aufruf leise.
#: Der P08-Stummel hat monatelang pro Aufruf gemeldet und niemand hat es gelesen.
#: ⚠️ Die Kehrseite: nach einem Neustart kommt genau eine Zeile und danach
#: Stille — im Log sieht ein Dauerzustand aus wie ein einmaliger Aussetzer.
#: Wer hier etwas sucht, prueft die Datei, nicht die Zeilenzahl.
_gemeldet: set[str] = set()


def _melde(dateiname: str, grund: str) -> None:
    if dateiname not in _gemeldet:
        _gemeldet.add(dateiname)
        logger.error(
            "[repo_prompt] %s nicht ladbar — Aufrufer laeuft auf seinem Notnagel. Grund: %s",
            dateiname,
            grund,
        )
    else:
        logger.debug("[repo_prompt] %s weiterhin nicht ladbar: %s", dateiname, grund)


def lade_repo_prompt(dateiname: str, *, platzhalter_probe: dict | None = None):
    """Laedt `backend/prompts/<dateiname>`. `None`, wenn er unbrauchbar ist.

    `None` statt einer Exception, weil jeder Aufrufer einen eingebauten
    Notnagel hat: ein fehlender Prompt macht ihn duemmer, aber nicht tot.

    `platzhalter_probe` ist das Dict, mit dem die Aufrufstelle spaeter
    `.format()` ruft. Passt das Template nicht dazu, faellt das HIER auf —
    also innerhalb des Rueckfalls. Ohne die Probe stuerbe `.format()` erst an
    der Aufrufstelle und damit ausserhalb jeder Absicherung: aus einem
    duemmeren Bot wuerde ein harter Ausfall.
    """
    from services.prompt_loader import LoadedPrompt, _extract_section

    pfad = os.path.join(_PROMPT_DIR, dateiname)
    if not os.path.exists(pfad):
        _melde(dateiname, f"Datei fehlt: {pfad}")
        return None

    try:
        with open(pfad, encoding="utf-8") as f:
            inhalt = f.read()

        system_prompt = _extract_section(inhalt, "System-Prompt")
        user_prompt = _extract_section(inhalt, "User-Prompt")
        if not system_prompt:
            raise ValueError("kein '## System-Prompt'-Abschnitt")
        if not user_prompt:
            raise ValueError("kein '## User-Prompt'-Abschnitt")
        if platzhalter_probe is not None:
            user_prompt.format(**platzhalter_probe)

        return LoadedPrompt(
            content=inhalt,
            system_prompt=system_prompt,
            user_prompt_template=user_prompt,
            sha=hashlib.sha256(inhalt.encode()).hexdigest(),
            loaded_at=datetime.now(UTC),
            source_path=pfad,
        )
    except Exception as exc:
        _melde(dateiname, f"{type(exc).__name__}: {exc}")
        return None
