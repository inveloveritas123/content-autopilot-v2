"""
Tests fuer patch_profile_field endpoint (Issue #113 Cowork review requirement).

Testet zwei zentrale Faelle:
1. Global slot (kein project_id): SELECT nutzt "project_id IS NULL",
   INSERT enthaelt KEINE project_id-Spalte
2. Project-scoped slot (project_id=<uuid>): SELECT nutzt "project_id = :pid",
   INSERT enthaelt project_id-Spalte mit :project_id-Parameter
"""
import asyncio
import json
import types
import uuid
from unittest.mock import AsyncMock, MagicMock, call


# ---------------------------------------------------------------------------
# Hilfsfunktion: Fake DB-Session bauen
# ---------------------------------------------------------------------------

def _make_fake_row(row_id=None, payload=None, version=1):
    """Erstellt eine Fake-Datenbankzeile mit id, payload, version."""
    row = types.SimpleNamespace(
        id=row_id or uuid.uuid4(),
        payload=payload or {"tonalitaet": "professionell", "kernthemen": ["Marketing"]},
        version=version,
    )
    return row


def _make_db_mock(fake_row):
    """
    Erstellt eine Mock-AsyncSession, die:
    - Beim ersten execute (SELECT) eine Fake-Row zurueckgibt
    - Beim zweiten execute (INSERT) und dritten execute (deactivate UPDATE) None zurueckgibt
    Zeichnet alle SQL-Strings auf.
    """
    executed_sqls = []
    executed_params = []

    async def fake_execute(sql_obj, params=None):
        sql_str = str(sql_obj)
        executed_sqls.append(sql_str)
        executed_params.append(params or {})

        result = MagicMock()
        # Erstes execute = SELECT (gibt Row zurueck)
        if len(executed_sqls) == 1:
            result.fetchone.return_value = fake_row
        else:
            result.fetchone.return_value = None
        return result

    db = MagicMock()
    db.execute = fake_execute
    db.commit = AsyncMock()

    return db, executed_sqls, executed_params


# ---------------------------------------------------------------------------
# Hilfsfunktion: Endpoint direkt aufrufen
# ---------------------------------------------------------------------------

async def _call_patch(tenant_id_str, profile_type, field_path, new_value, project_id, fake_row):
    """
    Ruft patch_profile_field direkt auf (ohne HTTP-Layer).
    Gibt zurueck: (response_dict, executed_sqls, executed_params)
    """
    from api.brand_voice import patch_profile_field, FieldEditRequest

    db, sqls, params = _make_db_mock(fake_row)
    auth_tenant_id = uuid.UUID(tenant_id_str)

    data = FieldEditRequest(field_path=field_path, new_value=new_value)

    result = await patch_profile_field(
        tenant_id=tenant_id_str,
        profile_type=profile_type,
        data=data,
        project_id=project_id,
        auth_tenant_id=auth_tenant_id,
        db=db,
    )
    return result, sqls, params


# ---------------------------------------------------------------------------
# Test 1: Globaler Slot (kein project_id)
# ---------------------------------------------------------------------------

def test_global_slot_select_uses_is_null():
    """SELECT fuer globalen Slot muss 'project_id IS NULL' enthalten."""
    tenant_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "professionell", "kernthemen": ["Marketing"]},
        version=3,
    )

    result, sqls, params = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="authentisch",
            project_id=None,
            fake_row=fake_row,
        )
    )

    select_sql = sqls[0]
    assert "project_id IS NULL" in select_sql, (
        f"Globaler SELECT muss 'project_id IS NULL' enthalten, got: {select_sql!r}"
    )


def test_global_slot_insert_omits_project_id_column():
    """INSERT fuer globalen Slot darf KEINE project_id-Spalte enthalten."""
    tenant_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "professionell", "kernthemen": ["Marketing"]},
        version=3,
    )

    result, sqls, params = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="authentisch",
            project_id=None,
            fake_row=fake_row,
        )
    )

    # sqls[1] = INSERT
    assert len(sqls) >= 2, f"Erwartet mindestens SELECT+INSERT, got {len(sqls)} SQLs"
    insert_sql = sqls[1]
    assert "INSERT" in insert_sql.upper(), f"sqls[1] sollte INSERT sein, got: {insert_sql!r}"
    assert "project_id" not in insert_sql, (
        f"Globaler INSERT darf kein 'project_id' enthalten, got: {insert_sql!r}"
    )


def test_global_slot_insert_params_omit_project_id():
    """INSERT-Parameter fuer globalen Slot duerfen kein 'project_id' enthalten."""
    tenant_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "professionell", "kernthemen": ["Marketing"]},
        version=3,
    )

    result, sqls, params_list = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="authentisch",
            project_id=None,
            fake_row=fake_row,
        )
    )

    insert_params = params_list[1]
    assert "project_id" not in insert_params, (
        f"INSERT-Parameter des globalen Slots duerfen kein 'project_id' enthalten, "
        f"got keys: {list(insert_params.keys())}"
    )


def test_global_slot_returns_correct_response():
    """Globaler Slot gibt korrekten Response-Dict zurueck."""
    tenant_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "professionell", "kernthemen": ["Marketing"]},
        version=5,
    )

    result, _, _ = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="authentisch",
            project_id=None,
            fake_row=fake_row,
        )
    )

    assert result["status"] == "updated"
    assert result["new_version"] == 6  # version 5 + 1
    assert result["project_id"] is None
    assert result["field_path"] == "tonalitaet"


# ---------------------------------------------------------------------------
# Test 2: Project-scoped Slot (mit project_id)
# ---------------------------------------------------------------------------

def test_project_slot_select_uses_project_id_param():
    """SELECT fuer project-scoped Slot muss 'project_id = :pid' enthalten."""
    tenant_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "casual", "kernthemen": ["Startup"]},
        version=2,
    )

    result, sqls, params = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="professionell",
            project_id=project_id,
            fake_row=fake_row,
        )
    )

    select_sql = sqls[0]
    assert "project_id = :pid" in select_sql, (
        f"Project-scoped SELECT muss 'project_id = :pid' enthalten, got: {select_sql!r}"
    )


def test_project_slot_select_not_uses_is_null():
    """Project-scoped SELECT darf NICHT 'project_id IS NULL' verwenden."""
    tenant_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "casual", "kernthemen": ["Startup"]},
        version=2,
    )

    result, sqls, _ = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="professionell",
            project_id=project_id,
            fake_row=fake_row,
        )
    )

    select_sql = sqls[0]
    assert "IS NULL" not in select_sql, (
        f"Project-scoped SELECT darf kein 'IS NULL' enthalten, got: {select_sql!r}"
    )


def test_project_slot_insert_contains_project_id_column():
    """INSERT fuer project-scoped Slot muss 'project_id' Spalte enthalten."""
    tenant_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "casual", "kernthemen": ["Startup"]},
        version=2,
    )

    result, sqls, _ = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="professionell",
            project_id=project_id,
            fake_row=fake_row,
        )
    )

    assert len(sqls) >= 2, f"Erwartet mindestens SELECT+INSERT, got {len(sqls)} SQLs"
    insert_sql = sqls[1]
    assert "INSERT" in insert_sql.upper(), f"sqls[1] sollte INSERT sein, got: {insert_sql!r}"
    assert "project_id" in insert_sql, (
        f"Project-scoped INSERT muss 'project_id' Spalte enthalten, got: {insert_sql!r}"
    )


def test_project_slot_insert_params_contain_project_id():
    """INSERT-Parameter fuer project-scoped Slot muessen 'project_id' enthalten."""
    tenant_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "casual", "kernthemen": ["Startup"]},
        version=2,
    )

    result, sqls, params_list = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="professionell",
            project_id=project_id,
            fake_row=fake_row,
        )
    )

    insert_params = params_list[1]
    assert "project_id" in insert_params, (
        f"INSERT-Parameter des project-scoped Slots muessen 'project_id' enthalten, "
        f"got keys: {list(insert_params.keys())}"
    )
    assert insert_params["project_id"] == project_id, (
        f"project_id im INSERT-Parameter muss mit Query-Param uebereinstimmen, "
        f"erwartet {project_id!r}, got {insert_params['project_id']!r}"
    )


def test_project_slot_insert_uses_colon_project_id_placeholder():
    """INSERT-SQL fuer project-scoped Slot muss ':project_id' Platzhalter enthalten."""
    tenant_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "casual", "kernthemen": ["Startup"]},
        version=2,
    )

    result, sqls, _ = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="professionell",
            project_id=project_id,
            fake_row=fake_row,
        )
    )

    insert_sql = sqls[1]
    assert ":project_id" in insert_sql, (
        f"Project-scoped INSERT-SQL muss ':project_id' Platzhalter enthalten, "
        f"got: {insert_sql!r}"
    )


def test_project_slot_returns_correct_response():
    """Project-scoped Slot gibt korrekten Response-Dict zurueck."""
    tenant_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "casual", "kernthemen": ["Startup"]},
        version=7,
    )

    result, _, _ = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="professionell",
            project_id=project_id,
            fake_row=fake_row,
        )
    )

    assert result["status"] == "updated"
    assert result["new_version"] == 8  # version 7 + 1
    assert result["project_id"] == project_id
    assert result["field_path"] == "tonalitaet"


# ---------------------------------------------------------------------------
# Test 3: Deactivate-SQL wird in beiden Faellen ausgefuehrt
# ---------------------------------------------------------------------------

def test_global_slot_deactivate_sql_executed():
    """Nach INSERT muss UPDATE (deactivate) ausgefuehrt werden — globaler Slot."""
    tenant_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "professionell", "kernthemen": ["Marketing"]},
    )

    _, sqls, _ = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="neu",
            project_id=None,
            fake_row=fake_row,
        )
    )

    assert len(sqls) == 3, f"Erwartet SELECT + INSERT + UPDATE, got {len(sqls)} SQLs: {sqls}"
    deactivate_sql = sqls[2]
    assert "UPDATE" in deactivate_sql.upper() and "is_active = false" in deactivate_sql, (
        f"sqls[2] sollte das Deactivate-UPDATE sein, got: {deactivate_sql!r}"
    )


def test_project_slot_deactivate_sql_executed():
    """Nach INSERT muss UPDATE (deactivate) ausgefuehrt werden — project-scoped Slot."""
    tenant_id = str(uuid.uuid4())
    project_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "casual", "kernthemen": ["Startup"]},
    )

    _, sqls, _ = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value="neu",
            project_id=project_id,
            fake_row=fake_row,
        )
    )

    assert len(sqls) == 3, f"Erwartet SELECT + INSERT + UPDATE, got {len(sqls)} SQLs: {sqls}"
    deactivate_sql = sqls[2]
    assert "UPDATE" in deactivate_sql.upper() and "is_active = false" in deactivate_sql, (
        f"sqls[2] sollte das Deactivate-UPDATE sein, got: {deactivate_sql!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: Edge-Cases
# ---------------------------------------------------------------------------

def test_unknown_profile_type_raises_422():
    """Unbekannter profile_type wird mit 422 abgelehnt."""
    from fastapi import HTTPException
    from api.brand_voice import patch_profile_field, FieldEditRequest

    tenant_id = str(uuid.uuid4())
    db = MagicMock()
    db.commit = AsyncMock()

    async def run():
        return await patch_profile_field(
            tenant_id=tenant_id,
            profile_type="unknown_type",
            data=FieldEditRequest(field_path="tonalitaet", new_value="x"),
            project_id=None,
            auth_tenant_id=uuid.UUID(tenant_id),
            db=db,
        )

    import pytest
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.status_code == 422


def test_invalid_field_path_raises_422():
    """Nicht-editierbares Feld wird mit 422 abgelehnt."""
    from fastapi import HTTPException
    from api.brand_voice import patch_profile_field, FieldEditRequest

    tenant_id = str(uuid.uuid4())
    db = MagicMock()
    db.commit = AsyncMock()

    async def run():
        return await patch_profile_field(
            tenant_id=tenant_id,
            profile_type="voice_profile",
            data=FieldEditRequest(field_path="not_allowed_field", new_value="x"),
            project_id=None,
            auth_tenant_id=uuid.UUID(tenant_id),
            db=db,
        )

    import pytest
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.status_code == 422


def test_tenant_mismatch_raises_403():
    """Anderer Tenant-ID im Pfad wird mit 403 abgelehnt."""
    from fastapi import HTTPException
    from api.brand_voice import patch_profile_field, FieldEditRequest

    tenant_id = str(uuid.uuid4())
    other_tenant_id = str(uuid.uuid4())
    db = MagicMock()
    db.commit = AsyncMock()

    async def run():
        return await patch_profile_field(
            tenant_id=other_tenant_id,   # anderer Tenant im Pfad
            profile_type="voice_profile",
            data=FieldEditRequest(field_path="tonalitaet", new_value="x"),
            project_id=None,
            auth_tenant_id=uuid.UUID(tenant_id),   # echter Auth-Tenant
            db=db,
        )

    import pytest
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.status_code == 403


def test_missing_active_row_raises_404():
    """Wenn keine aktive Row gefunden wird, muss 404 zurueckgegeben werden."""
    from fastapi import HTTPException
    from api.brand_voice import patch_profile_field, FieldEditRequest

    tenant_id = str(uuid.uuid4())

    async def fake_execute(sql_obj, params=None):
        result = MagicMock()
        result.fetchone.return_value = None  # kein aktives Profil
        return result

    db = MagicMock()
    db.execute = fake_execute
    db.commit = AsyncMock()

    async def run():
        return await patch_profile_field(
            tenant_id=tenant_id,
            profile_type="voice_profile",
            data=FieldEditRequest(field_path="tonalitaet", new_value="x"),
            project_id=None,
            auth_tenant_id=uuid.UUID(tenant_id),
            db=db,
        )

    import pytest
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(run())
    assert exc_info.value.status_code == 404


def test_xss_sanitization_in_string_value():
    """String-Werte werden HTML-escaped (XSS-Schutz)."""
    tenant_id = str(uuid.uuid4())
    fake_row = _make_fake_row(
        payload={"tonalitaet": "professionell", "kernthemen": ["Marketing"]},
        version=1,
    )

    result, sqls, params_list = asyncio.run(
        _call_patch(
            tenant_id_str=tenant_id,
            profile_type="voice_profile",
            field_path="tonalitaet",
            new_value='<script>alert("xss")</script>',
            project_id=None,
            fake_row=fake_row,
        )
    )

    insert_params = params_list[1]
    payload_str = insert_params["payload"]
    payload_dict = json.loads(payload_str)
    sanitized = payload_dict["tonalitaet"]
    assert "<script>" not in sanitized, (
        f"<script>-Tag muss HTML-escaped sein, got: {sanitized!r}"
    )
    assert "&lt;script&gt;" in sanitized, (
        f"Erwartet HTML-escapeten Wert, got: {sanitized!r}"
    )
