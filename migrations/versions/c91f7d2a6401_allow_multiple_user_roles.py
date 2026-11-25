"""Allow functional roles to be combined without losing existing assignments."""
from alembic import op
import sqlalchemy as sa

revision = 'c91f7d2a6401'
down_revision = 'b8d4e6f1a203'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user_roles') as batch:
        batch.drop_constraint('uq_user_roles_user_id', type_='unique')


def downgrade():
    # Restoring the old restriction must never discard accumulated roles.
    duplicates = op.get_bind().execute(sa.text(
        'SELECT user_id FROM user_roles GROUP BY user_id HAVING COUNT(*) > 1 LIMIT 1'
    )).first()
    if duplicates:
        raise RuntimeError('Downgrade bloqueado: existem usuarios com papeis multiplos')
    with op.batch_alter_table('user_roles') as batch:
        batch.create_unique_constraint('uq_user_roles_user_id', ['user_id'])
