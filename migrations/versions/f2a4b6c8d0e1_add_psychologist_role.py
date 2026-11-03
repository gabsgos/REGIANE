"""Add psychologist role for CRP professionals."""
from typing import Sequence
from alembic import context, op
import sqlalchemy as sa

revision: str = "f2a4b6c8d0e1"
down_revision: str | Sequence[str] | None = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None

def upgrade() -> None:
    if context.is_offline_mode():
        return
    bind = op.get_bind()
    roles = sa.table("roles", sa.column("id", sa.Integer()), sa.column("name", sa.String()), sa.column("description", sa.String()))
    exists = bind.execute(sa.select(roles.c.id).where(roles.c.name == "psicologo")).scalar()
    if exists is None:
        bind.execute(roles.insert().values(name="psicologo", description="Profissional clinico CRP"))

def downgrade() -> None:
    op.execute(sa.text("DELETE FROM roles WHERE name = 'psicologo'"))
