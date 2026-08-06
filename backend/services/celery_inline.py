"""Eine Celery-Task im selben Prozess ausfuehren — auch aus einer Task heraus.

`Task.apply()` fuehrt sofort und in-process aus; ein Broker ist dabei nie im
Spiel und das Ergebnis liegt vor, bevor `.get()` ueberhaupt gerufen wird.

Celerys Sperre gegen `result.get()` innerhalb einer Task zielt auf
`delay().get()` — dort wartet der Aufrufer auf einen ANDEREN Worker und kann
den Pool verhungern lassen. `EagerResult.get()` faellt unter dieselbe Sperre,
obwohl es nichts zu warten gibt: `celery.concurrency.prefork.process_initializer`
setzt `_set_task_join_will_block(True)` pauschal beim Worker-Start, und
`EagerResult.get()` prueft das Flag per Default (`disable_sync_subtasks=True`).

Was das am 06.08.2026 gekostet hat: `session_post_task` benutzte den
API-Helfer `_run_p12_p12b_pipeline` mit. P12 lief 34 s vollstaendig durch und
schrieb sein content_piece — `.get()` warf 1 ms spaeter
`RuntimeError: Never call result.get() within a task!`, P12b lief nie, und der
zugesagte Post kam nie an. Aus der API heraus lief exakt derselbe Code
fehlerfrei, weil das Flag im FastAPI-Prozess False ist. Ein Helfer, der aus
zwei Prozessarten gerufen wird, darf nicht von einem Prozess-Flag abhaengen.

Absichtlich KEIN `timeout`-Parameter: `EagerResult.get()` wertet ihn nicht aus
(die Task ist beim Aufruf laengst gelaufen). Die frueheren `timeout=120` in
p09/p13 waren wirkungslos — ein Parameter, der nichts tut, liest sich wie eine
Zusicherung, die es nicht gibt.
"""

from __future__ import annotations

from typing import Any

#: Nur fuer `Task.apply()`. Wer `delay()`/`apply_async()` benutzt, hat einen
#: echten Broker-Roundtrip vor sich — dort ist Celerys Sperre berechtigt und
#: darf nicht mit diesem Helfer umgangen werden.
__all__ = ["run_inline"]


def run_inline(task: Any, args: list | None = None, kwargs: dict | None = None) -> Any:
    """Fuehrt `task` synchron im aktuellen Prozess aus und gibt ihr Ergebnis zurueck.

    Wirft weiter, was die Task wirft (`propagate=True`, Celery-Default) — der
    Aufrufer behandelt Fachfehler wie bisher selbst.
    """
    ergebnis = task.apply(args=list(args or []), kwargs=dict(kwargs or {}))
    return ergebnis.get(disable_sync_subtasks=False)
