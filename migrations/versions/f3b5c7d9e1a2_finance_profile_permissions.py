"""Grant individual finance summary access to medical profiles."""

from alembic import op

revision = "f3b5c7d9e1a2"
down_revision = "f2a4b6c8d0e1"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
        WHERE r.name IN ('medico', 'psicologo') AND p.key = 'finance.read'
    """)


def downgrade():
    op.execute("""
        DELETE rp FROM role_permissions rp
        JOIN roles r ON r.id = rp.role_id
        JOIN permissions p ON p.id = rp.permission_id
        WHERE r.name IN ('medico', 'psicologo') AND p.key = 'finance.read'
    """)
