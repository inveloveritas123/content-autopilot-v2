"""Add slug column to tenants table — collision-free NC path generation

Revision ID: 034
Revises: 033
Create Date: 2026-05-03

Motivation: #134 — _slugify(tenants.name) can collide when two tenants share
similar names (e.g. "ZKG GmbH" and "Z.K.G. GmbH" both → "zkg-gmbh").
The slug column is UNIQUE, so collisions are caught at the DB level.
Backfill uses the same slugify logic as the old _slugify() helper so existing
NC paths are not broken.
"""
from alembic import op
import sqlalchemy as sa

revision = '034'
down_revision = '033'
branch_labels = None
depends_on = None


def upgrade():
    # Add slug column (nullable first for backfill)
    op.add_column('tenants', sa.Column('slug', sa.String(64), nullable=True))

    # Backfill: approximate _slugify() logic in SQL
    # Replace Umlaut digraphs, strip non-alphanumeric, collapse dashes, trim
    op.execute("""
        UPDATE tenants SET slug = LOWER(
            REGEXP_REPLACE(
                REGEXP_REPLACE(
                    REGEXP_REPLACE(
                        REGEXP_REPLACE(
                            REPLACE(REPLACE(REPLACE(REPLACE(LOWER(name), 'ä', 'ae'), 'ö', 'oe'), 'ü', 'ue'), 'ß', 'ss'),
                            '[^a-z0-9\\s-]', '', 'g'
                        ),
                        '[\\s_]+', '-', 'g'
                    ),
                    '-+', '-', 'g'
                ),
                '^-|-$', '', 'g'
            )
        )
        WHERE slug IS NULL
    """)

    # For any tenant that ended up with empty slug after transform, use id fallback
    op.execute("""
        UPDATE tenants SET slug = LEFT(REPLACE(id::text, '-', ''), 16)
        WHERE slug IS NULL OR slug = ''
    """)

    # If two tenants collide on the generated slug, append short ID suffix
    op.execute("""
        UPDATE tenants t SET slug = t.slug || '-' || LEFT(REPLACE(t.id::text, '-', ''), 8)
        WHERE EXISTS (
            SELECT 1 FROM tenants t2
            WHERE t2.slug = t.slug AND t2.id < t.id
        )
    """)

    # Now make NOT NULL + UNIQUE
    op.alter_column('tenants', 'slug', nullable=False)
    op.create_unique_constraint('uq_tenants_slug', 'tenants', ['slug'])


def downgrade():
    op.drop_constraint('uq_tenants_slug', 'tenants', type_='unique')
    op.drop_column('tenants', 'slug')
