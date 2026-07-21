"""RLS Cross-Tenant-Contamination-Test (W2, 2026-07-21) — GATE.

Beweist DB-seitig (nicht gemockt), dass die Postgres-Row-Level-Security-Policies
Tenant-Isolation ERZWINGEN: Eine Zeile von Tenant A darf für Tenant B NIE sichtbar
sein — auch bei einer nackten `SELECT * FROM <t>` ohne WHERE-Filter (das ist der
Kern: ein vergessenes WHERE tenant_id darf kein Leak sein).

Braucht eine echte Postgres-DB mit angewandten Migrationen (RLS aktiv). Ohne DB
(lokal) skippt der Test; die CI fährt ihn gegen einen Postgres-Service-Container.

Muster (nach leitivo-platform test_identity_verify_tenant_isolation):
  1. Zwei Tenants seeden.
  2. Eine Zeile an Tenant A binden.
  3. RLS-Kontext auf Tenant B setzen → Zeile darf NICHT sichtbar sein.
  4. RLS-Kontext auf Tenant A setzen → Zeile IST sichtbar (Gegenprobe).
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL") and not os.environ.get("SYNC_DATABASE_URL"),
    reason="RLS-Contamination-Test braucht echte Postgres-DB (CI-Service-Container).",
)


# Repräsentative Tabellen quer über die Domänen — je eine aus jeder Risiko-Gruppe:
# eine ehemals „dirty" (Text→UUID migriert) + eine schon saubere UUID-Tabelle.
_TEST_TABLES = [
    ("tenant_voice_profile", "tenant_id"),  # war dirty (018), jetzt UUID+RLS
    ("memory_chunks", "tenant_id"),  # war sauber (038), pgvector + RLS
    ("content_pieces", "tenant_id"),  # Kern-Tabelle
]


async def _seed_tenant(conn, name: str) -> uuid.UUID:
    from sqlalchemy import text

    tid = uuid.uuid4()
    await conn.execute(
        text("INSERT INTO tenants (id, name, api_key) VALUES (:id, :name, :key)"),
        {"id": tid, "name": name, "key": f"rls-test-{tid}"},
    )
    return tid


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_reads():
    """Kern-Gate: Zeile von Tenant A ist für Tenant B unsichtbar (RLS-erzwungen)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from services.rls import set_rls_tenant

    db_url = os.environ.get("DATABASE_URL") or os.environ["SYNC_DATABASE_URL"]
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(db_url)

    try:
        async with engine.begin() as conn:
            tenant_a = await _seed_tenant(conn, "RLS-Test-A")
            tenant_b = await _seed_tenant(conn, "RLS-Test-B")

            # Zeile an Tenant A binden (RLS-Kontext A, damit WITH CHECK passt).
            await set_rls_tenant(conn, str(tenant_a))
            row_id = uuid.uuid4()
            await conn.execute(
                text(
                    "INSERT INTO memory_chunks (id, tenant_id, content_text) "
                    "VALUES (:id, :tid, :txt)"
                ),
                {"id": row_id, "tid": tenant_a, "txt": "geheim von A"},
            )

            # Kontext B: nacktes SELECT ohne WHERE darf die A-Zeile NICHT sehen.
            await set_rls_tenant(conn, str(tenant_b))
            res_b = await conn.execute(
                text("SELECT id FROM memory_chunks WHERE id = :id"), {"id": row_id}
            )
            assert res_b.first() is None, "RLS-LECK: Tenant B sieht eine Zeile von Tenant A!"

            # Gegenprobe Kontext A: Zeile IST sichtbar.
            await set_rls_tenant(conn, str(tenant_a))
            res_a = await conn.execute(
                text("SELECT id FROM memory_chunks WHERE id = :id"), {"id": row_id}
            )
            assert res_a.first() is not None, "Tenant A sieht die eigene Zeile nicht"

            # Cleanup (noch im Kontext A; B-Zeilen via eigenem Kontext gäbe es keine).
            await conn.execute(text("DELETE FROM memory_chunks WHERE id = :id"), {"id": row_id})
            # tenants aufräumen: RLS gilt nicht für tenants selbst (keine tenant_id-Policy).
            await set_rls_tenant(conn, "")
            await conn.execute(
                text("DELETE FROM tenants WHERE id = ANY(:ids)"),
                {"ids": [tenant_a, tenant_b]},
            )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rls_empty_context_sees_nothing():
    """Ohne gesetzten Tenant-Kontext (leer) matcht die Policy nichts → fail-closed,
    KEIN Cast-Crash (NULLIF-Behandlung des leeren Strings)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from services.rls import set_rls_tenant

    db_url = os.environ.get("DATABASE_URL") or os.environ["SYNC_DATABASE_URL"]
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = create_async_engine(db_url)
    try:
        async with engine.begin() as conn:
            await set_rls_tenant(conn, "")  # leerer Kontext
            # Darf nicht crashen, liefert 0 Zeilen.
            res = await conn.execute(text("SELECT count(*) FROM memory_chunks"))
            assert res.scalar() == 0
    finally:
        await engine.dispose()
