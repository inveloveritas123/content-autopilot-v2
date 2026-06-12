#!/usr/bin/env python3
"""
prompt_health.py — Health-Check fuer alle content-truth Prompt-Dateien.

Laedt jede Datei aus PROMPT_PATHS direkt via LocalFsStorageAdapter und
prueft System-Prompt / User-Prompt-Extraktion.

Ausgabe pro Prompt (TSV-aehnlich):
  KEY | system_chars | user_chars | fences_balanced | STATUS | grund

STATUS = ok   → alles in Ordnung
STATUS = WEIRD → leerer System-Prompt, fehlende Sektionen, unbalancierte Fences

WICHTIG: Dieses Skript importiert KEIN google-Paket.
services/__init__.py wuerde google.generativeai importieren — das wird
umgangen indem nur die benoedigten Modul-Dateien direkt per importlib geladen
werden, ohne das services-Package zu initialisieren.

Ausfuehren:
    CONTENT_TRUTH_BASE_PATH=/pfad/zu/content-truth python3 scripts/prompt_health.py

Defaults (wenn ENV nicht gesetzt):
    CONTENT_TRUTH_BASE_PATH = <repo-root>/content-truth
    (Repo-Root = zwei Ebenen ueber diesem Skript: backend/scripts/ → backend/ → repo-root)
"""
import importlib.util
import os
import sys
import types

# ---------------------------------------------------------------------------
# Stub fuer google-Pakete (verhindert ImportError falls trotzdem irgendwo
# ein transitiver Import stattfindet)
# ---------------------------------------------------------------------------
for _pkg in ("google", "google.generativeai", "anthropic", "httpx"):
    if _pkg not in sys.modules:
        _m = types.ModuleType(_pkg)
        sys.modules[_pkg] = _m

# ---------------------------------------------------------------------------
# Direkte Modul-Lader (umgehen services/__init__.py)
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_SCRIPTS_DIR)
_REPO_ROOT = os.path.dirname(_BACKEND_DIR)

# PYTHONPATH sicherstellen
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


def _load_module_from_file(module_name: str, file_path: str) -> types.ModuleType:
    """Laedt ein Python-Modul direkt aus Dateipfad ohne __init__.py-Trigger."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Minimale Stubs fuer pydantic-settings / config.py
try:
    import pydantic_settings  # noqa: F401
    _config = _load_module_from_file(
        "config",
        os.path.join(_BACKEND_DIR, "config.py"),
    )
except Exception:
    # Fallback-Stub fuer config, wenn pydantic-settings fehlt
    _config_mod = types.ModuleType("config")
    _settings_stub = types.SimpleNamespace(
        content_truth_base_path="/app/content-truth",
        prompt_storage_backend="localfs",
        content_truth_overlay_path="/app/data/prompts-custom",
    )
    _config_mod.settings = _settings_stub
    sys.modules["config"] = _config_mod

# brand_voice_storage direkt laden (braucht config + httpx)
_bvs = _load_module_from_file(
    "services.brand_voice_storage",
    os.path.join(_BACKEND_DIR, "services", "brand_voice_storage.py"),
)

# local_fs_storage direkt laden
_lfs = _load_module_from_file(
    "services.local_fs_storage",
    os.path.join(_BACKEND_DIR, "services", "local_fs_storage.py"),
)

# prompt_loader direkt laden
_pl = _load_module_from_file(
    "services.prompt_loader",
    os.path.join(_BACKEND_DIR, "services", "prompt_loader.py"),
)

# prompt_health_core direkt laden (enthaelt die wiederverwendbare Logik)
_phc = _load_module_from_file(
    "services.prompt_health_core",
    os.path.join(_BACKEND_DIR, "services", "prompt_health_core.py"),
)

# ---------------------------------------------------------------------------
# Imports aus den geladenen Modulen
# ---------------------------------------------------------------------------
from services.local_fs_storage import LocalFsStorageAdapter  # noqa: E402
from services.prompt_loader import PROMPT_PATHS              # noqa: E402
from services.prompt_health_core import check_prompt_content  # noqa: E402

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

_DEFAULT_CONTENT_TRUTH = os.path.join(_REPO_ROOT, "content-truth")
CONTENT_TRUTH_BASE_PATH = os.environ.get(
    "CONTENT_TRUTH_BASE_PATH", _DEFAULT_CONTENT_TRUTH
)


# ---------------------------------------------------------------------------
# Health-Check (nutzt prompt_health_core)
# ---------------------------------------------------------------------------

def run_health_check() -> list[dict]:
    """Fuehrt den Health-Check fuer alle PROMPT_PATHS durch."""
    adapter = LocalFsStorageAdapter(base_dir=CONTENT_TRUTH_BASE_PATH)
    results = []

    for key, rel_path in PROMPT_PATHS.items():
        row: dict = {
            "key": key,
            "path": rel_path,
            "system_chars": 0,
            "user_chars": 0,
            "fences_balanced": True,
            "status": "ok",
            "grund": "",
        }

        # Datei lesen
        try:
            raw = adapter.read(rel_path)
            content = raw.decode("utf-8")
        except Exception as exc:
            row["status"] = "WEIRD"
            row["grund"] = f"DATEI_NICHT_LESBAR: {exc}"
            results.append(row)
            continue

        # Health-Check via prompt_health_core
        result = check_prompt_content(content, prompt_key=key)

        row["system_chars"] = result.system_chars
        row["user_chars"] = result.user_chars
        row["fences_balanced"] = result.fences_balanced

        if result.issues:
            row["status"] = "WEIRD"
            row["grund"] = ", ".join(result.issues)

        results.append(row)

    return results


# ---------------------------------------------------------------------------
# Ausgabe
# ---------------------------------------------------------------------------

def _fmt_bool(b: bool) -> str:
    return "yes" if b else "NO"


def print_table(results: list[dict]) -> None:
    """Gibt die Ergebnisse als lesbare Tabelle aus."""
    header = f"{'KEY':<14} {'sys_chars':>10} {'usr_chars':>10} {'fences_ok':>10}  {'STATUS':<7}  grund"
    sep = "-" * 80
    print(header)
    print(sep)

    weird_count = 0
    for r in results:
        status = r["status"]
        if status == "WEIRD":
            weird_count += 1
        grund = r["grund"] or "-"
        print(
            f"{r['key']:<14} {r['system_chars']:>10} {r['user_chars']:>10} "
            f"{_fmt_bool(r['fences_balanced']):>10}  {status:<7}  {grund}"
        )

    print(sep)
    total = len(results)
    ok_count = total - weird_count
    print(f"Gesamt: {total} | ok: {ok_count} | WEIRD: {weird_count}")
    print(f"content-truth Basis: {CONTENT_TRUTH_BASE_PATH}")

    if weird_count:
        print()
        print("WEIRD-Prompts (Chris muss ran):")
        for r in results:
            if r["status"] == "WEIRD":
                print(f"  - {r['key']} ({r['path']}): {r['grund']}")


if __name__ == "__main__":
    results = run_health_check()
    print_table(results)
    # Exit-Code 1 wenn WEIRD-Eintraege vorhanden
    sys.exit(1 if any(r["status"] == "WEIRD" for r in results) else 0)
