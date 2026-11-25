import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_role_migration_preserves_assignments_and_blocks_lossy_downgrade():
    path = Path(__file__).parents[1] / 'migrations/versions/c91f7d2a6401_allow_multiple_user_roles.py'
    spec = importlib.util.spec_from_file_location('role_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(sa.text('CREATE TABLE user_roles (user_id INTEGER NOT NULL, role_id INTEGER NOT NULL, PRIMARY KEY(user_id,role_id), CONSTRAINT uq_user_roles_user_id UNIQUE(user_id))'))
        connection.execute(sa.text('INSERT INTO user_roles VALUES (1,1)'))
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
            connection.execute(sa.text('INSERT INTO user_roles VALUES (1,2)'))
            with pytest.raises(RuntimeError, match='papeis multiplos'):
                module.downgrade()
            assert connection.scalar(sa.text('SELECT count(*) FROM user_roles')) == 2
            connection.execute(sa.text('DELETE FROM user_roles WHERE role_id=2'))
            module.downgrade()
            assert connection.scalar(sa.text('SELECT count(*) FROM user_roles')) == 1
            module.upgrade()
            assert connection.scalar(sa.text('SELECT count(*) FROM user_roles')) == 1
