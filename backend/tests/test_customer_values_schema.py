"""
test_customer_values_schema.py — Schritt-1-Tests für Issue #43 (Schema + Resolver).

Deckt ab:
  1. TABLE_MAP enthält 'customer_values' → 'tenant_customer_values' (4. Eintrag).
  2. is_canonical() akzeptiert 'values-v1.0' und weiterhin bestehende p0X-Muster.
  3. pick_active() funktioniert für customer_values-Rows identisch wie für Zwillinge.
  4. Migration 053 ist syntaktisch valides Python und trägt den freigabe-robert-Kopfkommentar.

Dep-frei via importlib (umgeht services/__init__ + sqlalchemy/celery/models).
Anti-Pollution: alle Stubs nur mit `if name not in sys.modules`-Guards.

Reihenfolge-Unabhängigkeit: Modul wird via importlib.util geladen, nicht via normales
`import` — kein Konflikt mit anderen Testdateien, die services stubben.
"""

import ast
import importlib.util
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Dep-freier Loader für canonical_profiles — identisch zu test_canonical_profiles.py
# ---------------------------------------------------------------------------

def _load_canonical_profiles():
    p = Path(__file__).parent.parent / "services" / "canonical_profiles.py"
    spec = importlib.util.spec_from_file_location("canonical_profiles_43_test", str(p))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


cp = _load_canonical_profiles()


# ---------------------------------------------------------------------------
# 1. TABLE_MAP — 4. Eintrag vorhanden
# ---------------------------------------------------------------------------

class TestTableMap:
    def test_customer_values_registered(self):
        assert "customer_values" in cp.TABLE_MAP, (
            "TABLE_MAP muss 'customer_values' enthalten (Issue #43 Schritt 1)"
        )

    def test_customer_values_table_name(self):
        assert cp.TABLE_MAP["customer_values"] == "tenant_customer_values"

    def test_all_four_entries_present(self):
        assert set(cp.TABLE_MAP) == {
            "customer_context",
            "voice_profile",
            "audience_avatar",
            "customer_values",
        }

    def test_existing_entries_unchanged(self):
        """Bestehende Einträge dürfen nicht verändert worden sein."""
        assert cp.TABLE_MAP["customer_context"] == "tenant_customer_context"
        assert cp.TABLE_MAP["voice_profile"] == "tenant_voice_profile"
        assert cp.TABLE_MAP["audience_avatar"] == "tenant_audience_avatar"


# ---------------------------------------------------------------------------
# 2. is_canonical — Regex erweitert um 'values'-Präfix
# ---------------------------------------------------------------------------

class TestIsCanonicalExtended:
    # Neue Werte-Quelle muss akzeptiert werden
    def test_values_v1_0_is_canonical(self):
        assert cp.is_canonical({"_meta": {"prompt_version": "values-v1.0"}}) is True

    def test_values_v2_3_is_canonical(self):
        assert cp.is_canonical({"_meta": {"prompt_version": "values-v2.3"}}) is True

    # Bestehende p0X müssen weiterhin funktionieren (Regression)
    def test_p01_still_canonical(self):
        assert cp.is_canonical({"_meta": {"prompt_version": "p01-v1.0"}}) is True

    def test_p03_still_canonical(self):
        assert cp.is_canonical({"_meta": {"prompt_version": "p03-v1.0"}}) is True

    def test_p04_still_canonical(self):
        assert cp.is_canonical({"_meta": {"prompt_version": "p04-v1.0"}}) is True

    def test_p09_still_canonical(self):
        assert cp.is_canonical({"_meta": {"prompt_version": "p09-v1.0"}}) is True

    # Ungültige Muster müssen weiterhin abgelehnt werden
    def test_plain_values_rejected(self):
        """'values' ohne -vN.N ist kein gültiges Muster."""
        assert cp.is_canonical({"_meta": {"prompt_version": "values"}}) is False

    def test_p17_rejected(self):
        """'p17-v1.0' ist kein gültiges Muster (p0X → nur einstellige p0-Gruppe)."""
        # p17 hat 2 Ziffern nach 'p' → p0[0-9]+ greift für p01..p09, p17 wäre 'p1' nicht 'p0'
        # → False erwartet (Muster: p0[0-9]+)
        assert cp.is_canonical({"_meta": {"prompt_version": "p17-v1.0"}}) is False

    def test_legacy_without_meta_rejected(self):
        assert cp.is_canonical({"tonalitaet": {}}) is False

    def test_none_rejected(self):
        assert cp.is_canonical(None) is False

    def test_arbitrary_string_rejected(self):
        assert cp.is_canonical({"_meta": {"prompt_version": "legacy-v1.0"}}) is False


# ---------------------------------------------------------------------------
# 3. pick_active — funktioniert identisch für customer_values-Rows
# ---------------------------------------------------------------------------

class TestPickActiveForCustomerValues:
    """Stellt sicher, dass pick_active() mit customer_values-ähnlichen Rows
    dasselbe Verhalten zeigt wie mit voice/avatar-Rows (generischer Resolver)."""

    def _make_row(self, project_id, version, payload):
        return {"project_id": project_id, "version": version, "payload": payload}

    def test_empty_returns_none(self):
        assert cp.pick_active([]) is None

    def test_global_row_selected_without_project(self):
        rows = [
            self._make_row("proj-A", 9, {"werte": [{"wert": "Qualität"}]}),
            self._make_row(None, 2, {"werte": [{"wert": "Vertrauen"}]}),
        ]
        result = cp.pick_active(rows)
        assert result["payload"]["werte"][0]["wert"] == "Vertrauen"

    def test_project_scoped_row_wins(self):
        rows = [
            self._make_row(None, 5, {"werte": [{"wert": "global"}]}),
            self._make_row("proj-A", 1, {"werte": [{"wert": "proj-spezifisch"}]}),
        ]
        result = cp.pick_active(rows, project_id="proj-A")
        assert result["payload"]["werte"][0]["wert"] == "proj-spezifisch"

    def test_highest_version_wins(self):
        rows = [
            self._make_row(None, 1, {"werte": [{"wert": "alt"}]}),
            self._make_row(None, 7, {"werte": [{"wert": "aktuell"}]}),
        ]
        assert cp.pick_active(rows)["payload"]["werte"][0]["wert"] == "aktuell"

    def test_customer_values_row_is_canonical_with_values_version(self):
        payload = {
            "werte": [{"wert": "Ehrlichkeit", "status": "aktiv"}],
            "_meta": {"prompt_version": "values-v1.0"},
        }
        assert cp.is_canonical(payload) is True


# ---------------------------------------------------------------------------
# 4. Migration 053 — Syntaxcheck + freigabe-robert-Kopfkommentar
# ---------------------------------------------------------------------------

class TestMigration053:
    _migration_path = (
        Path(__file__).parent.parent
        / "alembic"
        / "versions"
        / "053_customer_values.py"
    )

    def test_migration_file_exists(self):
        assert self._migration_path.exists(), (
            f"Migration 053 nicht gefunden: {self._migration_path}"
        )

    def test_migration_is_valid_python(self):
        source = self._migration_path.read_text(encoding="utf-8")
        try:
            ast.parse(source)
        except SyntaxError as e:
            raise AssertionError(f"Migration 053 ist kein valides Python: {e}") from e

    def test_migration_has_freigabe_comment(self):
        source = self._migration_path.read_text(encoding="utf-8")
        assert "freigabe-robert" in source, (
            "Migration 053 muss den Kopfkommentar 'freigabe-robert' tragen."
        )

    def test_migration_revision_is_053(self):
        source = self._migration_path.read_text(encoding="utf-8")
        assert "revision = '053'" in source

    def test_migration_creates_tenant_customer_values(self):
        source = self._migration_path.read_text(encoding="utf-8")
        assert "tenant_customer_values" in source

    def test_migration_has_entity_type_column(self):
        """entity_type-Spalte auf voice_drift_observation muss enthalten sein."""
        source = self._migration_path.read_text(encoding="utf-8")
        assert "entity_type" in source
        assert "voice_drift_observation" in source

    def test_migration_has_coalesce_index(self):
        source = self._migration_path.read_text(encoding="utf-8")
        assert "COALESCE" in source
        assert "uq_tenant_customer_values_active" in source

    def test_migration_has_source_check_new_values(self):
        """Die 2 neuen source-Werte müssen im CHECK-Constraint stehen."""
        source = self._migration_path.read_text(encoding="utf-8")
        assert "memory_promotion" in source
        assert "p17_update" in source

    def test_migration_downgrade_is_symmetric(self):
        """downgrade() muss die Tabelle und die entity_type-Spalte droppen."""
        source = self._migration_path.read_text(encoding="utf-8")
        assert "drop_table" in source or "DROP TABLE" in source
        assert "drop_column" in source or "DROP COLUMN" in source
