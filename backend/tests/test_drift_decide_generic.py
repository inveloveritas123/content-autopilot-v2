"""
test_drift_decide_generic.py — Schritt-4-Tests für Issue #43.

P17-Vorbau: decide_drift_observation entitäts-generisch.

Abgedeckt:
  1. _ENTITY_TABLE-Map vollständig und korrekt.
  2. get_entity_table() löst entity_type → Tabellenname auf.
  3. apply_drift_changes() — op:"set" (bestehend, Rückwärtskompatibilität).
  4. apply_drift_changes() — op:"append" hängt Element an eine Liste an.
  5. apply_drift_changes() — op:"append" auf Nicht-Liste → ValueError (422-Kandidat).
  6. apply_drift_changes() — ungültiger Pfad wird still geskippt (Dict-only-Walker).
  7. Tenant-Isolation: entity_type aus der Observation entscheidet die Zieltabelle,
     nicht ein hartkodiertes Literal.
  8. Regressions-Nachweis: voice-entity_type gibt dieselbe Zieltabelle wie vor der
     Generalisierung (tenant_voice_profile).

Dep-frei via importlib — keine sqlalchemy/fastapi/celery-Abhängigkeiten.
Anti-Pollution: Stubs nur mit `if name not in sys.modules`-Guards.
"""

import importlib.util
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Dep-freier Loader für brand_voice_drift_helpers
# ---------------------------------------------------------------------------

_HELPERS_PATH = (
    Path(__file__).parent.parent / "api" / "brand_voice_drift_helpers.py"
)


def _load_helpers():
    """Lädt brand_voice_drift_helpers.py dep-frei via importlib."""
    spec = importlib.util.spec_from_file_location(
        "brand_voice_drift_helpers_test", str(_HELPERS_PATH)
    )
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


h = _load_helpers()


# ---------------------------------------------------------------------------
# 1. _ENTITY_TABLE vollständig
# ---------------------------------------------------------------------------


class TestEntityTable:
    def test_voice_maps_to_tenant_voice_profile(self):
        assert h._ENTITY_TABLE["voice"] == "tenant_voice_profile"

    def test_values_maps_to_tenant_customer_values(self):
        assert h._ENTITY_TABLE["values"] == "tenant_customer_values"

    def test_avatar_maps_to_tenant_audience_avatar(self):
        assert h._ENTITY_TABLE["avatar"] == "tenant_audience_avatar"

    def test_context_maps_to_tenant_customer_context(self):
        assert h._ENTITY_TABLE["context"] == "tenant_customer_context"

    def test_exactly_four_entries(self):
        assert set(h._ENTITY_TABLE.keys()) == {"voice", "values", "avatar", "context"}


# ---------------------------------------------------------------------------
# 2. get_entity_table()
# ---------------------------------------------------------------------------


class TestGetEntityTable:
    def test_voice_resolves(self):
        assert h.get_entity_table("voice") == "tenant_voice_profile"

    def test_values_resolves(self):
        assert h.get_entity_table("values") == "tenant_customer_values"

    def test_avatar_resolves(self):
        assert h.get_entity_table("avatar") == "tenant_audience_avatar"

    def test_context_resolves(self):
        assert h.get_entity_table("context") == "tenant_customer_context"

    def test_unknown_entity_raises_value_error(self):
        import pytest
        with pytest.raises(ValueError, match="Unbekannter entity_type"):
            h.get_entity_table("unknown_entity")

    def test_none_raises_value_error(self):
        import pytest
        with pytest.raises(ValueError, match="Unbekannter entity_type"):
            h.get_entity_table(None)

    def test_empty_string_raises_value_error(self):
        import pytest
        with pytest.raises(ValueError, match="Unbekannter entity_type"):
            h.get_entity_table("")

    def test_default_voice_same_as_explicit_voice(self):
        """entity_type fehlt → Default 'voice' → identisches Ergebnis wie explizit 'voice'."""
        # get_entity_table ohne Argument verwendet den Default
        assert h.get_entity_table() == h.get_entity_table("voice")


# ---------------------------------------------------------------------------
# 3. apply_drift_changes() — op:"set" (bestehend)
# ---------------------------------------------------------------------------


class TestApplyDriftChangesSet:
    def _base_payload(self):
        return {
            "tonalitaet": {"grundton": "professionell"},
            "kernthemen": ["Marketing", "Leadership"],
            "werte": [{"wert": "Ehrlichkeit", "gewicht": 1.0}],
        }

    def test_set_simple_nested_field(self):
        payload = self._base_payload()
        changes = [{"field_path": "tonalitaet.grundton", "op": "set", "new_value": "authentisch"}]
        result = h.apply_drift_changes(payload, changes, {})
        assert result["tonalitaet"]["grundton"] == "authentisch"

    def test_set_with_default_op(self):
        """op fehlt → Default ist 'set'."""
        payload = self._base_payload()
        # kein 'op' → verhält sich wie 'set'
        changes = [{"field_path": "tonalitaet.grundton", "new_value": "locker"}]
        result = h.apply_drift_changes(payload, changes, {})
        assert result["tonalitaet"]["grundton"] == "locker"

    def test_set_uses_suggested_value_when_new_value_is_none(self):
        payload = self._base_payload()
        changes = [{"field_path": "tonalitaet.grundton", "op": "set", "new_value": None}]
        suggested = {"tonalitaet.grundton": "suggestiert"}
        result = h.apply_drift_changes(payload, changes, suggested)
        assert result["tonalitaet"]["grundton"] == "suggestiert"

    def test_set_invalid_path_skipped_silently(self):
        """Ungültiger Pfad → silent skip, Payload bleibt unverändert."""
        payload = self._base_payload()
        changes = [{"field_path": "nonexistent.field", "op": "set", "new_value": "wert"}]
        result = h.apply_drift_changes(payload, changes, {})
        assert result == self._base_payload()

    def test_set_does_not_mutate_original_payload(self):
        """apply_drift_changes arbeitet auf einer Deep-Copy, nicht am Original."""
        original = self._base_payload()
        import copy
        original_copy = copy.deepcopy(original)
        changes = [{"field_path": "tonalitaet.grundton", "op": "set", "new_value": "neu"}]
        h.apply_drift_changes(original, changes, {})
        assert original == original_copy

    def test_set_multiple_changes(self):
        payload = self._base_payload()
        changes = [
            {"field_path": "tonalitaet.grundton", "op": "set", "new_value": "authentisch"},
            # kernthemen ist keine Dict-Navigation → Pfad "kernthemen" hat nur 1 Part
            # → Setzen direkt auf Root nicht möglich via Dict-only-Walker (parts[-1] in cursor)
        ]
        result = h.apply_drift_changes(payload, changes, {})
        assert result["tonalitaet"]["grundton"] == "authentisch"


# ---------------------------------------------------------------------------
# 4. apply_drift_changes() — op:"append"
# ---------------------------------------------------------------------------


class TestApplyDriftChangesAppend:
    def _base_payload(self):
        return {
            "werte": [{"wert": "Ehrlichkeit", "gewicht": 1.0}],
            "kernthemen": ["Marketing"],
        }

    def test_append_adds_element_to_list(self):
        payload = self._base_payload()
        new_wert = {"wert": "Transparenz", "gewicht": 0.9}
        changes = [{"field_path": "werte", "op": "append", "new_value": new_wert}]
        result = h.apply_drift_changes(payload, changes, {})
        assert len(result["werte"]) == 2
        assert result["werte"][1] == new_wert

    def test_append_preserves_existing_elements(self):
        payload = self._base_payload()
        new_wert = {"wert": "Qualität", "gewicht": 0.8}
        changes = [{"field_path": "werte", "op": "append", "new_value": new_wert}]
        result = h.apply_drift_changes(payload, changes, {})
        # Bestehendes Element unverändert
        assert result["werte"][0] == {"wert": "Ehrlichkeit", "gewicht": 1.0}

    def test_append_multiple_times(self):
        payload = self._base_payload()
        changes = [
            {"field_path": "werte", "op": "append", "new_value": {"wert": "A"}},
            {"field_path": "werte", "op": "append", "new_value": {"wert": "B"}},
        ]
        result = h.apply_drift_changes(payload, changes, {})
        assert len(result["werte"]) == 3
        assert result["werte"][1]["wert"] == "A"
        assert result["werte"][2]["wert"] == "B"

    def test_append_does_not_mutate_original_payload(self):
        original = self._base_payload()
        import copy
        original_copy = copy.deepcopy(original)
        changes = [{"field_path": "werte", "op": "append", "new_value": {"wert": "neu"}}]
        h.apply_drift_changes(original, changes, {})
        assert original == original_copy

    def test_append_uses_suggested_value_when_new_value_is_none(self):
        payload = self._base_payload()
        new_wert = {"wert": "aus_suggested"}
        changes = [{"field_path": "werte", "op": "append", "new_value": None}]
        suggested = {"werte": new_wert}
        result = h.apply_drift_changes(payload, changes, suggested)
        assert len(result["werte"]) == 2
        assert result["werte"][1] == new_wert

    def test_append_to_simple_string_list(self):
        payload = {"kernthemen": ["Marketing"]}
        changes = [{"field_path": "kernthemen", "op": "append", "new_value": "Leadership"}]
        result = h.apply_drift_changes(payload, changes, {})
        assert result["kernthemen"] == ["Marketing", "Leadership"]


# ---------------------------------------------------------------------------
# 5. append auf Nicht-Liste → ValueError
# ---------------------------------------------------------------------------


class TestAppendOnNonList:
    def test_append_on_dict_field_raises(self):
        import pytest
        payload = {"tonalitaet": {"grundton": "professionell"}}
        changes = [{"field_path": "tonalitaet", "op": "append", "new_value": {"x": 1}}]
        with pytest.raises(ValueError, match="append.*keine Liste"):
            h.apply_drift_changes(payload, changes, {})

    def test_append_on_string_field_raises(self):
        import pytest
        payload = {"name": "Muster GmbH"}
        changes = [{"field_path": "name", "op": "append", "new_value": " GmbH"}]
        with pytest.raises(ValueError, match="append.*keine Liste"):
            h.apply_drift_changes(payload, changes, {})

    def test_append_path_not_found_raises(self):
        """Pfad existiert nicht → Feld nicht da → silent skip (kein Fehler)."""
        # Wenn der Pfad nicht existiert → skip. Fehler nur wenn Pfad existiert
        # aber kein list-Typ ist. Nicht existierender Pfad → skip wie bei set.
        payload = {"werte": [{"wert": "x"}]}
        changes = [{"field_path": "nicht_vorhanden", "op": "append", "new_value": "y"}]
        # Kein Fehler — Pfad existiert einfach nicht, skip
        result = h.apply_drift_changes(payload, changes, {})
        assert result == {"werte": [{"wert": "x"}]}


# ---------------------------------------------------------------------------
# 6. Regressions-Nachweis: voice → tenant_voice_profile (IDENTITY)
# ---------------------------------------------------------------------------


class TestVoiceEntityTypeRegression:
    """
    Stellt sicher, dass entity_type='voice' (oder fehlend via Default)
    exakt 'tenant_voice_profile' ergibt — identisch zum hartkodieren Literal
    das vorher in brand_voice.py stand (Zeilen 811, 856, 870).
    """

    def test_explicit_voice_gives_tenant_voice_profile(self):
        assert h.get_entity_table("voice") == "tenant_voice_profile"

    def test_default_entity_type_gives_tenant_voice_profile(self):
        """Kein Argument → Default 'voice' → tenant_voice_profile."""
        assert h.get_entity_table() == "tenant_voice_profile"

    def test_voice_table_is_not_any_other_table(self):
        """Kleiner Smoke: voice darf nicht versehentlich values-Tabelle zurückgeben."""
        voice_table = h.get_entity_table("voice")
        values_table = h.get_entity_table("values")
        assert voice_table != values_table


# ---------------------------------------------------------------------------
# 7. Tenant-Isolation-Nachweis (konzeptionell)
# ---------------------------------------------------------------------------


class TestTenantIsolationConcept:
    """
    Die eigentliche Tenant-Isolation liegt in der SQL-Query
    (WHERE tenant_id = :t). Hier testen wir die Helper-Seite:
    Die Entity-Table-Map gibt für jeden entity_type immer dieselbe
    Tabelle zurück — unabhängig von irgendwelchen Input-Werten außer
    dem entity_type selbst. Kein User-Input fließt in den Tabellennamen.
    """

    def test_entity_table_output_is_immutable_for_same_input(self):
        t1 = h.get_entity_table("values")
        t2 = h.get_entity_table("values")
        assert t1 == t2

    def test_entity_table_is_from_whitelist(self):
        """Alle Tabellennamen müssen aus der Whitelist stammen."""
        allowed = {
            "tenant_voice_profile",
            "tenant_customer_values",
            "tenant_audience_avatar",
            "tenant_customer_context",
        }
        for entity_type in ["voice", "values", "avatar", "context"]:
            assert h.get_entity_table(entity_type) in allowed

    def test_sql_injection_attempt_raises(self):
        """Böswillige entity_type-Werte werden durch ValueError blockiert."""
        import pytest
        malicious_inputs = [
            "voice; DROP TABLE tenant_voice_profile;",
            "' OR '1'='1",
            "values UNION SELECT",
        ]
        for bad_input in malicious_inputs:
            with pytest.raises(ValueError):
                h.get_entity_table(bad_input)
