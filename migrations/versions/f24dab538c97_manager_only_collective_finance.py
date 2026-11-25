"""Remove retired individual finance grants; combined managers retain their grants."""
from alembic import op
import sqlalchemy as sa

revision = 'f24dab538c97'
down_revision = 'e13c9b427a86'
branch_labels = None
depends_on = None


def upgrade():
    op.execute(sa.text("DELETE FROM role_permissions WHERE role_id IN (SELECT id FROM roles WHERE name IN ('medico','psicologo')) AND permission_id IN (SELECT id FROM permissions WHERE `key`='finance.read')"))


def downgrade():
    # Restore only the previous summary/read grant, never managerial finance actions.
    op.execute(sa.text("INSERT INTO role_permissions(role_id,permission_id) SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.name IN ('medico','psicologo') AND p.`key`='finance.read' AND NOT EXISTS (SELECT 1 FROM role_permissions rp WHERE rp.role_id=r.id AND rp.permission_id=p.id)"))
