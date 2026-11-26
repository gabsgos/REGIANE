"""Allow date-specific professional working hours."""

import sqlalchemy as sa
from alembic import op

revision = "c6d9f2b8e104"
down_revision = "b5c8e4a7d901"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("professional_day_overrides") as batch:
        batch.add_column(sa.Column("start_time", sa.Time(), nullable=True))
        batch.add_column(sa.Column("end_time", sa.Time(), nullable=True))


def downgrade():
    with op.batch_alter_table("professional_day_overrides") as batch:
        batch.drop_column("end_time")
        batch.drop_column("start_time")
