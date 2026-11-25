"""Seed the permission used to start and finalize clinical examinations."""
from alembic import op
import sqlalchemy as sa

revision = 'a4e75c1d902b'
down_revision = 'f24dab538c97'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("""
        INSERT INTO permissions (`key`, resource, action, sensitivity, delegable, active)
        VALUES ('clinical_queue.write', 'clinical_worklist', 'write', 'HIGH_CLINICAL', 0, 1)
    """))
    op.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT roles.id, permissions.id FROM roles CROSS JOIN permissions
        WHERE roles.name IN ('gerente', 'medico', 'psicologo') AND permissions.`key` = 'clinical_queue.write'
    """))


def downgrade():
    op.execute(sa.text("""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE `key` = 'clinical_queue.write')
    """))
    op.execute(sa.text("DELETE FROM permissions WHERE `key` = 'clinical_queue.write'"))
