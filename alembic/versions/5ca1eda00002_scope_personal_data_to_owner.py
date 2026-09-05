"""scope personal business data (products, sales, transactions, credit, customers) to their owner

Revision ID: 5ca1eda00002
Revises: c0ffee000001
Create Date: 2026-09-05 11:00:00.000000

These tables previously held a single global feed shared by every personal
account. Legacy rows cannot be attributed to an owner, so they are removed
as part of moving to per-user isolation.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5ca1eda00002'
down_revision: Union[str, Sequence[str], None] = 'c0ffee000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ['products', 'sales', 'transactions', 'credit_entries', 'customers']


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"DELETE FROM {table}")
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column('user_id', sa.String(length=36), nullable=False))
            batch.create_index(f'ix_{table}_user_id', ['user_id'], unique=False)
            batch.create_foreign_key(
                f'fk_{table}_user_id_users',
                'users',
                ['user_id'],
                ['id'],
                ondelete='CASCADE',
            )


def downgrade() -> None:
    for table in reversed(_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f'fk_{table}_user_id_users', type_='foreignkey')
            batch.drop_index(f'ix_{table}_user_id')
            batch.drop_column('user_id')