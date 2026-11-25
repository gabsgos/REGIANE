"""Complete ownership metadata; existing records belong to HRP by user approval."""
from alembic import op
import sqlalchemy as sa

revision = 'd02b8a316f75'
down_revision = 'c91f7d2a6401'
branch_labels = None
depends_on = None

TABLES = ('service_types', 'payment_items', 'financial_accounts', 'receipts', 'document_deliveries')


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column('workspace_id', sa.BigInteger(), nullable=True, server_default='1'))
        op.create_index('ix_' + table + '_workspace_id', table, ['workspace_id'])


def downgrade():
    for table in reversed(TABLES):
        op.drop_index('ix_' + table + '_workspace_id', table_name=table)
        op.drop_column(table, 'workspace_id')
