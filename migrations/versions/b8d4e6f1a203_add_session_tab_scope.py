"""Add tab scope to authenticated sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d4e6f1a203"
down_revision: str | Sequence[str] | None = "a7c9e1d2f4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_sessions", sa.Column("tab_id_hash", sa.String(64), nullable=True))
    op.create_index("ix_auth_sessions_tab_id_hash", "auth_sessions", ["tab_id_hash"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_tab_id_hash", table_name="auth_sessions")
    op.drop_column("auth_sessions", "tab_id_hash")
