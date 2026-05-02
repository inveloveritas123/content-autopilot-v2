"""Add brand voice tables: customer context, voice profile, audience avatar,
wizard session, drift observation, daily cost tracking, setup pipeline runs.

Revision ID: 018
Revises: 017
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = '018'
down_revision = '017'


def upgrade() -> None:
    # 1. tenant_customer_context
    op.create_table(
        'tenant_customer_context',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('source', sa.Text(),
                  sa.CheckConstraint(
                      "source IN ('transcript','md_upload','json_upload','nc_import',"
                      "'wizard','manual_edit','drift_update')",
                      name='ck_tenant_customer_context_source'
                  )),
        sa.Column('source_meta', JSONB()),
        sa.Column('payload', JSONB(), nullable=False),
        sa.Column('prompt_version_hash', sa.Text(), nullable=False),
        sa.Column('model_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_by', sa.Text()),
    )
    op.create_index(
        'ix_tenant_customer_context_tenant_id',
        'tenant_customer_context',
        ['tenant_id'],
    )
    op.create_index(
        'uq_tenant_customer_context_active',
        'tenant_customer_context',
        ['tenant_id'],
        unique=True,
        postgresql_where=sa.text('is_active = true'),
    )

    # 2. tenant_voice_profile
    op.create_table(
        'tenant_voice_profile',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('source', sa.Text(),
                  sa.CheckConstraint(
                      "source IN ('transcript','md_upload','json_upload','nc_import',"
                      "'wizard','manual_edit','drift_update')",
                      name='ck_tenant_voice_profile_source'
                  )),
        sa.Column('source_meta', JSONB()),
        sa.Column('payload', JSONB(), nullable=False),
        sa.Column('prompt_version_hash', sa.Text(), nullable=False),
        sa.Column('model_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_by', sa.Text()),
    )
    op.create_index(
        'ix_tenant_voice_profile_tenant_id',
        'tenant_voice_profile',
        ['tenant_id'],
    )
    op.create_index(
        'uq_tenant_voice_profile_active',
        'tenant_voice_profile',
        ['tenant_id'],
        unique=True,
        postgresql_where=sa.text('is_active = true'),
    )

    # 3. tenant_audience_avatar
    op.create_table(
        'tenant_audience_avatar',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('source', sa.Text(),
                  sa.CheckConstraint(
                      "source IN ('transcript','md_upload','json_upload','nc_import',"
                      "'wizard','manual_edit','drift_update')",
                      name='ck_tenant_audience_avatar_source'
                  )),
        sa.Column('source_meta', JSONB()),
        sa.Column('payload', JSONB(), nullable=False),
        sa.Column('prompt_version_hash', sa.Text(), nullable=False),
        sa.Column('model_id', sa.Text(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('created_by', sa.Text()),
    )
    op.create_index(
        'ix_tenant_audience_avatar_tenant_id',
        'tenant_audience_avatar',
        ['tenant_id'],
    )
    op.create_index(
        'uq_tenant_audience_avatar_active',
        'tenant_audience_avatar',
        ['tenant_id'],
        unique=True,
        postgresql_where=sa.text('is_active = true'),
    )

    # 4. wizard_session
    op.create_table(
        'wizard_session',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('current_phase', sa.Integer(), nullable=False, server_default=sa.text('1'),
                  comment='1..6'),
        sa.Column('answers', JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('inline_hints_history', JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('phase_synthesis', JSONB(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column('status', sa.Text(),
                  sa.CheckConstraint(
                      "status IN ('in_progress','paused','finalized','abandoned')",
                      name='ck_wizard_session_status'
                  ),
                  server_default=sa.text("'in_progress'")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.CheckConstraint(
            'current_phase >= 1 AND current_phase <= 6',
            name='ck_wizard_session_current_phase',
        ),
    )
    op.create_index(
        'ix_wizard_session_tenant_id',
        'wizard_session',
        ['tenant_id'],
    )

    # 5. voice_drift_observation
    op.create_table(
        'voice_drift_observation',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('trigger_post_ids', ARRAY(UUID(as_uuid=True)), nullable=False),
        sa.Column('current_voice_version', sa.Integer(), nullable=False),
        sa.Column('suggested_changes', JSONB(), nullable=False),
        sa.Column('status', sa.Text(),
                  sa.CheckConstraint(
                      "status IN ('pending_review','accepted','rejected','partial')",
                      name='ck_voice_drift_observation_status'
                  ),
                  server_default=sa.text("'pending_review'")),
        sa.Column('user_feedback', JSONB()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index(
        'ix_voice_drift_observation_tenant_id',
        'voice_drift_observation',
        ['tenant_id'],
    )

    # 6. daily_cost_tenant  (composite PK, no UUID id)
    op.create_table(
        'daily_cost_tenant',
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('cost_usd', sa.Numeric(10, 4), server_default=sa.text('0')),
        sa.Column('call_count', sa.Integer(), server_default=sa.text('0')),
        sa.Column('notified_at', sa.TIMESTAMP(timezone=True)),
        sa.PrimaryKeyConstraint('tenant_id', 'date', name='pk_daily_cost_tenant'),
    )

    # 7. setup_pipeline_run
    op.create_table(
        'setup_pipeline_run',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('stage', sa.Text(),
                  sa.CheckConstraint(
                      "stage IN ('p01','p03','p04','md_convert','orchestrator')",
                      name='ck_setup_pipeline_run_stage'
                  )),
        sa.Column('model_id', sa.Text()),
        sa.Column('prompt_version_hash', sa.Text()),
        sa.Column('input_tokens', sa.Integer()),
        sa.Column('output_tokens', sa.Integer()),
        sa.Column('cost_usd', sa.Numeric(10, 4)),
        sa.Column('duration_ms', sa.Integer()),
        sa.Column('status', sa.Text(),
                  sa.CheckConstraint(
                      "status IN ('queued','running','done','failed','paused_for_cost')",
                      name='ck_setup_pipeline_run_status'
                  )),
        sa.Column('error_meta', JSONB()),
        sa.Column('output_hash', sa.Text()),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('finished_at', sa.TIMESTAMP(timezone=True)),
    )
    op.create_index(
        'ix_setup_pipeline_run_tenant_id',
        'setup_pipeline_run',
        ['tenant_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_setup_pipeline_run_tenant_id', 'setup_pipeline_run')
    op.drop_table('setup_pipeline_run')

    op.drop_table('daily_cost_tenant')

    op.drop_index('ix_voice_drift_observation_tenant_id', 'voice_drift_observation')
    op.drop_table('voice_drift_observation')

    op.drop_index('ix_wizard_session_tenant_id', 'wizard_session')
    op.drop_table('wizard_session')

    op.drop_index('uq_tenant_audience_avatar_active', 'tenant_audience_avatar')
    op.drop_index('ix_tenant_audience_avatar_tenant_id', 'tenant_audience_avatar')
    op.drop_table('tenant_audience_avatar')

    op.drop_index('uq_tenant_voice_profile_active', 'tenant_voice_profile')
    op.drop_index('ix_tenant_voice_profile_tenant_id', 'tenant_voice_profile')
    op.drop_table('tenant_voice_profile')

    op.drop_index('uq_tenant_customer_context_active', 'tenant_customer_context')
    op.drop_index('ix_tenant_customer_context_tenant_id', 'tenant_customer_context')
    op.drop_table('tenant_customer_context')
