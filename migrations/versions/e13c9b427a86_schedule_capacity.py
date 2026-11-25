"""Daily extra capacity, date overrides and collective sessions."""
from alembic import op
import sqlalchemy as sa

revision = 'e13c9b427a86'
down_revision = 'd02b8a316f75'
branch_labels = None
depends_on = None


def columns():
    return [sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column('workspace_id', sa.BigInteger(), nullable=True, server_default='1'),
            sa.Column('professional_id', sa.BigInteger(), sa.ForeignKey('professionals.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now())]


def upgrade():
    op.create_table('professional_schedule_rules', *columns(),
        sa.Column('weekday', sa.Integer(), nullable=False),
        sa.Column('limit_mode', sa.String(10), nullable=False),
        sa.Column('extra_limit', sa.Integer()), sa.Column('closed', sa.Boolean(), nullable=False),
        sa.Column('start_time', sa.Time()), sa.Column('end_time', sa.Time()),
        sa.UniqueConstraint('workspace_id', 'professional_id', 'weekday'))
    op.create_table('professional_day_overrides', *columns(),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('limit_mode', sa.String(10), nullable=False),
        sa.Column('extra_limit', sa.Integer()), sa.Column('closed', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.String(255), nullable=False),
        sa.UniqueConstraint('workspace_id', 'professional_id', 'day'))
    op.create_table('schedule_sessions', *columns(),
        sa.Column('starts_at', sa.DateTime(), nullable=False),
        sa.Column('capacity', sa.Integer(), nullable=False), sa.Column('status', sa.String(20), nullable=False))
    for table in ('professional_schedule_rules', 'professional_day_overrides', 'schedule_sessions'):
        op.create_index('ix_' + table + '_workspace_id', table, ['workspace_id'])
    with op.batch_alter_table('appointments') as batch:
        batch.add_column(sa.Column('booking_kind', sa.String(30), nullable=False, server_default='DETRAN_OFICIAL'))
        batch.add_column(sa.Column('schedule_session_id', sa.BigInteger()))
        batch.add_column(sa.Column('previous_appointment_id', sa.BigInteger()))
        batch.create_foreign_key('fk_appointments_schedule_session_id_schedule_sessions', 'schedule_sessions', ['schedule_session_id'], ['id'])
        batch.create_foreign_key('fk_appointments_previous_appointment_id_appointments', 'appointments', ['previous_appointment_id'], ['id'])
    op.execute(sa.text("UPDATE appointments SET booking_kind='LEGACY' WHERE source_kind='LEGACY'"))


def downgrade():
    # No appointment is removed; future booking metadata is removed only on explicit rollback.
    with op.batch_alter_table('appointments') as batch:
        batch.drop_constraint('fk_appointments_previous_appointment_id_appointments', type_='foreignkey')
        batch.drop_constraint('fk_appointments_schedule_session_id_schedule_sessions', type_='foreignkey')
        batch.drop_column('previous_appointment_id')
        batch.drop_column('schedule_session_id')
        batch.drop_column('booking_kind')
    for table in ('schedule_sessions', 'professional_day_overrides', 'professional_schedule_rules'):
        op.drop_table(table)
