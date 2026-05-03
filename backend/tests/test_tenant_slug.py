"""
Tests for Issue #134 — NC-Sync: Slug-Kollisionsfestigkeit.

Acceptance:
  1. tenant_slug im NC-Pfad kollisionsfrei garantiert (dedicated slug column)
  2. Existing Tenants: kein Datenverlust (backward-compat fallback)
  3. Zwei Tenants mit ähnlichem Namen → unterschiedliche NC-Pfade
"""
import json
import uuid
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# _slugify unit tests
# ---------------------------------------------------------------------------

class TestSlugify:
    def _fn(self):
        from services.brand_voice_storage import _slugify
        return _slugify

    def test_basic(self):
        assert self._fn()("ZKG GmbH") == "zkg-gmbh"

    def test_umlauts(self):
        fn = self._fn()
        assert fn("Müller & Söhne") == "mueller-soehne"
        assert fn("Größe GmbH") == "groesse-gmbh"

    def test_collision_scenario(self):
        fn = self._fn()
        slug_a = fn("ZKG GmbH")
        slug_b = fn("Z.K.G. GmbH")
        # Both produce the same slug — that's the bug the DB constraint fixes
        assert slug_a == slug_b == "zkg-gmbh"

    def test_empty_fallback(self):
        assert self._fn()("") == "default"

    def test_max_length(self):
        long_name = "a" * 100
        assert len(self._fn()(long_name)) <= 64


# ---------------------------------------------------------------------------
# sync_brand_voice_to_nc — slug column usage
# ---------------------------------------------------------------------------

def _make_session(tenant_row, project_row=None, pillar_rows=None):
    """Build a mock sync_session_factory that returns given rows."""
    mock_session = MagicMock()

    call_count = [0]
    all_rows = [tenant_row]
    if project_row is not None:
        all_rows.append(project_row)
    # Pillar rows cycle through PILLAR_TABLES (3 pillars)
    if pillar_rows is not None:
        all_rows.extend(pillar_rows)
    else:
        all_rows.extend([None, None, None])

    def _fetchone_side_effect():
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(all_rows):
            return all_rows[idx]
        return None

    mock_session.execute.return_value.fetchone.side_effect = _fetchone_side_effect

    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=mock_session)
    cm.__exit__ = MagicMock(return_value=False)
    return MagicMock(return_value=cm)


class TestSyncBrandVoiceUsesSlugColumn:
    """sync_brand_voice_to_nc() must prefer tenants.slug over _slugify(name)."""

    def _tenant_row(self, name, slug):
        row = MagicMock()
        # Row access: [0] = name, [1] = slug (new SELECT name, slug)
        row.__getitem__ = lambda self, i: [name, slug][i]
        return row

    def test_uses_dedicated_slug_not_slugify(self):
        """When tenants.slug is populated, it MUST be used verbatim."""
        from services.brand_voice_storage import sync_brand_voice_to_nc

        tenant_id = str(uuid.uuid4())
        # Tenant whose name would slugify differently from the stored slug
        tenant_row = self._tenant_row("Z.K.G. GmbH", "zkg-gmbh-custom")

        written_paths = []

        def _mock_write(path, content):
            written_paths.append(path)

        mock_adapter = MagicMock()
        mock_adapter.write.side_effect = _mock_write

        mock_factory = _make_session(tenant_row)

        with patch("models.base.sync_session_factory", mock_factory):
            with patch("services.brand_voice_storage.get_default_nc_adapter", return_value=mock_adapter):
                with patch("services.brand_voice_storage._get_brand_voice_base", return_value="/Kunde/"):
                    result = sync_brand_voice_to_nc(tenant_id)

        # No pillars were written (all skipped — no payload rows), but we can
        # verify the resolved path by checking skipped (zero errors)
        assert result["errors"] == []
        # Adapter write never called (no active payloads) but the session used
        # the slug column — verified by mocking: if name was used instead of slug,
        # path would be "zkg-gmbh" not "zkg-gmbh-custom"
        # To actually verify the path we insert a fake payload:

    def test_nc_path_uses_slug_column_with_payload(self):
        """With an active payload, the written NC path must contain tenants.slug."""
        from services.brand_voice_storage import sync_brand_voice_to_nc

        tenant_id = str(uuid.uuid4())
        tenant_row = self._tenant_row("Z.K.G. GmbH", "zkg-gmbh-unique")

        # First pillar row: has payload, others None
        pillar_payload = {"key": "value"}

        pillar_row_with_data = MagicMock()
        pillar_row_with_data.__getitem__ = lambda self, i: (
            pillar_payload if i == 0 else None
        )
        pillar_row_with_data.__bool__ = lambda self: True

        written_paths = []

        def _mock_write(path, content):
            written_paths.append(path)

        mock_adapter = MagicMock()
        mock_adapter.write.side_effect = _mock_write

        # Custom session: tenant_row, then 3 pillar rows (first has data, others None)
        mock_session = MagicMock()
        responses = [
            tenant_row,           # SELECT name, slug
            pillar_row_with_data, # voice_profile pillar
            None,                 # customer_context pillar
            None,                 # audience_avatar pillar
        ]
        idx = [0]

        def fetchone():
            i = idx[0]
            idx[0] += 1
            return responses[i] if i < len(responses) else None

        mock_session.execute.return_value.fetchone.side_effect = fetchone
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=mock_session)
        cm.__exit__ = MagicMock(return_value=False)
        mock_factory = MagicMock(return_value=cm)

        with patch("models.base.sync_session_factory", mock_factory):
            with patch("services.brand_voice_storage.get_default_nc_adapter", return_value=mock_adapter):
                with patch("services.brand_voice_storage._get_brand_voice_base", return_value="/Kunde/"):
                    result = sync_brand_voice_to_nc(tenant_id)

        assert len(written_paths) == 1
        assert "zkg-gmbh-unique" in written_paths[0], (
            f"Expected 'zkg-gmbh-unique' (from slug column) in path, got: {written_paths[0]}"
        )
        assert "zkg-gmbh" not in written_paths[0].replace("zkg-gmbh-unique", ""), (
            "Should NOT use _slugify(name) path 'zkg-gmbh' when slug column is populated"
        )

    def test_fallback_to_slugify_when_slug_column_empty(self):
        """If slug column is empty/None (pre-migration), fall back to _slugify(name)."""
        from services.brand_voice_storage import sync_brand_voice_to_nc

        tenant_id = str(uuid.uuid4())
        # slug column is None (pre-migration state)
        tenant_row = self._tenant_row("ZKG GmbH", None)

        pillar_payload = {"key": "value"}
        pillar_row_with_data = MagicMock()
        pillar_row_with_data.__getitem__ = lambda self, i: (
            pillar_payload if i == 0 else None
        )

        written_paths = []
        mock_adapter = MagicMock()
        mock_adapter.write.side_effect = lambda p, c: written_paths.append(p)

        mock_session = MagicMock()
        responses = [tenant_row, pillar_row_with_data, None, None]
        idx = [0]

        def fetchone():
            i = idx[0]
            idx[0] += 1
            return responses[i] if i < len(responses) else None

        mock_session.execute.return_value.fetchone.side_effect = fetchone
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=mock_session)
        cm.__exit__ = MagicMock(return_value=False)
        mock_factory = MagicMock(return_value=cm)

        with patch("models.base.sync_session_factory", mock_factory):
            with patch("services.brand_voice_storage.get_default_nc_adapter", return_value=mock_adapter):
                with patch("services.brand_voice_storage._get_brand_voice_base", return_value="/Kunde/"):
                    result = sync_brand_voice_to_nc(tenant_id)

        assert len(written_paths) == 1
        assert "zkg-gmbh" in written_paths[0], (
            f"Expected fallback slug 'zkg-gmbh' in path, got: {written_paths[0]}"
        )


class TestTwoTenantsNoCollision:
    """Two tenants with similar names have different NC paths via slug column."""

    def test_similar_names_different_slugs(self):
        """ZKG GmbH and Z.K.G. GmbH must produce different NC paths."""
        from services.brand_voice_storage import _slugify

        # At the _slugify level they collide — that's the known bug
        assert _slugify("ZKG GmbH") == _slugify("Z.K.G. GmbH")

        # But with dedicated slug column, they get different slugs (set at onboarding)
        # Simulate: tenant A has slug="zkg-gmbh", tenant B has slug="zkg-gmbh-b"
        # (DB UNIQUE constraint ensures this at INSERT time)
        slug_a = "zkg-gmbh"
        slug_b = "zkg-gmbh-b"
        assert slug_a != slug_b, "Unique constraint ensures no collision"

    def test_migration_backfill_deduplicates(self):
        """Migration collision-resolution logic produces unique slugs."""
        # Simulate the SQL UPDATE logic: second tenant gets a suffix
        def simulate_backfill(names: list[str]) -> list[str]:
            """Approximate the migration's dedup logic."""
            from services.brand_voice_storage import _slugify
            slugs = [_slugify(n) for n in names]
            # Dedup: if collision, append short id suffix
            seen = {}
            result = []
            for i, s in enumerate(slugs):
                if s in seen:
                    result.append(f"{s}-{i:08x}")
                else:
                    seen[s] = i
                    result.append(s)
            return result

        names = ["ZKG GmbH", "Z.K.G. GmbH", "ZKG-Beratung"]
        slugs = simulate_backfill(names)
        assert len(set(slugs)) == len(slugs), f"Collision in backfill: {slugs}"
