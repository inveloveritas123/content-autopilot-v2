"""Add Telegram integration tables: tenant link, message log, bot session.

Revision ID: 019
Revises: 018
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = '019'
down_revision = '018'


def upgrade() -> None:
    # 1. tenant_telegram_link
    op.create_table(
        'tenant_telegram_link',
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
        sa.Column('telegram_chat_id', sa.BigInteger(), nullable=False),
        sa.Column('linked_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('confirmed_via_token', sa.Text()),
        sa.Column('status', sa.Text(),
                  sa.CheckConstraint(
                      "status IN ('pending','active','blocked')",
                      name='ck_tenant_telegram_link_status'
                  ),
                  nullable=False, server_default=sa.text("'pending'")),
        sa.PrimaryKeyConstraint('tenant_id', 'telegram_user_id', name='pk_tenant_telegram_link'),
    )
    op.create_index(
        'ix_tenant_telegram_link_tenant_id',
        'tenant_telegram_link',
        ['tenant_id'],
    )

    # 2. telegram_message_log
    op.create_table(
        'telegram_message_log',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('direction', sa.Text(),
                  sa.CheckConstraint(
                      "direction IN ('in','out')",
                      name='ck_telegram_message_log_direction'
                  ),
                  nullable=False),
        sa.Column('message_type', sa.Text(),
                  sa.CheckConstraint(
                      "message_type IN ('voice','text','photo')",
                      name='ck_telegram_message_log_message_type'
                  ),
                  nullable=False),
        sa.Column('original_payload', JSONB()),
        sa.Column('transcript_text', sa.Text()),
        sa.Column('transcription_confidence', sa.Numeric(3, 2)),
        sa.Column('transcription_model', sa.Text()),
        sa.Column('extracted_intent', sa.Text()),
        sa.Column('extracted_features', JSONB()),
        sa.Column('flagged_for_review', sa.Boolean(), nullable=False,
                  server_default=sa.text('false')),
        sa.Column('flag_reasons', ARRAY(sa.Text())),
        sa.Column('routed_to', sa.Text(),
                  sa.CheckConstraint(
                      "routed_to IN ('p08_response','p10','voice_feedback','help','close','reviewer_queue')",
                      name='ck_telegram_message_log_routed_to'
                  )),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
    )
    op.create_index(
        'ix_telegram_message_log_tenant_id',
        'telegram_message_log',
        ['tenant_id'],
    )

    # 3. bot_session
    op.create_table(
        'bot_session',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('mode', sa.Text(),
                  sa.CheckConstraint(
                      "mode IN ('targeted','random_smart')",
                      name='ck_bot_session_mode'
                  ),
                  nullable=False),
        sa.Column('topic_idea_id', UUID(as_uuid=True)),
        sa.ForeignKeyConstraint(
            ['topic_idea_id'], ['content_ideas.id'],
            name='fk_bot_session_topic_idea_id',
            ondelete='SET NULL',
        ),
        sa.Column('current_question_index', sa.Integer(), nullable=False,
                  server_default=sa.text('1')),
        sa.Column('messages', JSONB(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column('status', sa.Text(),
                  sa.CheckConstraint(
                      "status IN ('active','closed','expired')",
                      name='ck_bot_session_status'
                  ),
                  nullable=False, server_default=sa.text("'active'")),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()')),
        sa.Column('last_message_at', sa.TIMESTAMP(timezone=True)),
    )
    op.create_index(
        'ix_bot_session_tenant_id',
        'bot_session',
        ['tenant_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_bot_session_tenant_id', 'bot_session')
    op.drop_table('bot_session')

    op.drop_index('ix_telegram_message_log_tenant_id', 'telegram_message_log')
    op.drop_table('telegram_message_log')

    op.drop_index('ix_tenant_telegram_link_tenant_id', 'tenant_telegram_link')
    op.drop_table('tenant_telegram_link')
