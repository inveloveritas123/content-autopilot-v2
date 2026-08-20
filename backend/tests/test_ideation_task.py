"""Tests fuer tasks.ideation_task — RLS-Kontext beim PK-Read (SSOT AP1.1, 21.08.).

`auto_generate_ideas` bekommt von der Pipeline-Pumpe nur die item_id. Der PK-Read
(`session.get(SourceItem, item_id)`) lief bislang OHNE jeden RLS-Kontext — unter
FORCE ROW LEVEL SECURITY (Migration 058) liefert das still `None`, der Task meldet
"item_not_found" fuer ein real existierendes Item. Belegt: die Pumpe stiess alle
10 Minuten 30 Ideation-Tasks an, jede Runde 30x "item_not_found", endlos (Worker-Log
48h) — Louis' Vorwurf "nichts funktioniert" wortwoertlich im Betrieb.

Fix analog generate_task.py:analyze_item (Regression ed90abf): Bypass NUR fuer den
PK-Read, danach sofort eng auf den Tenant-Kontext.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import tasks.ideation_task  # noqa: F401  — muss vor den @patch-Decorators im Modul-Cache stehen


def _make_session(item):
    """Session-Stub: .get() liefert das Item, RLS-Setter sind einzeln mockbar."""
    session = MagicMock()
    session.get.return_value = item
    return session


def _make_item(tenant_id="tenant-x", analysis="vorhanden"):
    item = MagicMock()
    item.id = "item-1"
    item.tenant_id = tenant_id
    item.analysis = analysis
    item.title = "Titel"
    item.transcript_text = "Transkript"
    return item


class TestRlsContextVorPkRead:
    @patch("services.rls.set_rls_tenant_sync")
    @patch("services.rls.set_rls_bypass_sync")
    @patch("tasks.ideation_task.sync_session_factory")
    def test_bypass_wird_vor_dem_pk_read_gesetzt(
        self, mock_factory, mock_bypass, mock_set_rls_tenant
    ):
        """Regression: ohne Bypass liefert session.get() unter FORCE RLS still None.

        Dieser Test waere mit dem alten Code (Bypass-Aufruf fehlt) GRUEN
        geblieben, weil die gemockte Session immer das praeparierte Item
        liefert — er prueft deshalb den Aufruf selbst, nicht nur, dass
        `auto_generate_ideas` irgendein Ergebnis zurueckgibt.
        """
        item = _make_item()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=_make_session(item))
        ctx.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = ctx

        with patch(
            "services.content_ideation.run_ideation_pipeline",
            return_value=[],
        ):
            from tasks.ideation_task import auto_generate_ideas

            auto_generate_ideas("item-1")

        # Bypass muss VOR dem eng gesetzten Tenant-Kontext aktiviert UND
        # wieder deaktiviert worden sein (analog generate_task.py).
        mock_bypass.assert_any_call(ctx.__enter__.return_value, True)
        mock_bypass.assert_any_call(ctx.__enter__.return_value, False)
        mock_set_rls_tenant.assert_any_call(ctx.__enter__.return_value, "tenant-x")

    @patch("services.rls.set_rls_tenant_sync")
    @patch("services.rls.set_rls_bypass_sync")
    @patch("tasks.ideation_task.sync_session_factory")
    def test_item_not_found_bleibt_erhalten_wenn_wirklich_nichts_da_ist(
        self, mock_factory, mock_bypass, mock_set_rls_tenant
    ):
        """Fail-Pfad bleibt unveraendert: existiert das Item wirklich nicht,
        meldet der Task weiterhin item_not_found — kein falsches Grün."""
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=_make_session(None))
        ctx.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = ctx

        from tasks.ideation_task import auto_generate_ideas

        ergebnis = auto_generate_ideas("item-fehlt")

        assert ergebnis == {"error": "item_not_found"}


class TestRegenerateIdeasRlsContext:
    @patch("tasks.ideation_task.auto_generate_ideas")
    @patch("services.rls.set_rls_tenant_sync")
    @patch("services.rls.set_rls_bypass_sync")
    @patch("tasks.ideation_task.sync_session_factory")
    def test_regenerate_setzt_ebenfalls_bypass_vor_pk_read(
        self, mock_factory, mock_bypass, mock_set_rls_tenant, mock_auto_generate
    ):
        """regenerate_ideas hat denselben PK-Read-Bug wie auto_generate_ideas —
        gleiche Fix-Klasse, gleicher Nachweis."""
        item = _make_item()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=_make_session(item))
        ctx.__exit__ = MagicMock(return_value=False)
        mock_factory.return_value = ctx
        mock_auto_generate.return_value = {"status": "success"}

        from tasks.ideation_task import regenerate_ideas

        regenerate_ideas("item-1", force=False)

        mock_bypass.assert_any_call(ctx.__enter__.return_value, True)
        mock_bypass.assert_any_call(ctx.__enter__.return_value, False)
        mock_set_rls_tenant.assert_any_call(ctx.__enter__.return_value, "tenant-x")
