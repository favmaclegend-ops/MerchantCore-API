"""add user_id to notifications and scope them to owners

Revision ID: c0ffee000001
Revises: 63d9223d341e
Create Date: 2026-09-05 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c0ffee000001'
down_revision: Union[str, Sequence[str], None] = '63d9223d341e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Legacy notifications were a global feed with no owner; they cannot be
    # attributed after the fact, so they are removed as part of moving to a
    # per-user feed.
    op.execute("DELETE FROM notifications")
    with op.batch_alter_table('notifications') as batch:
        batch.add_column(sa.Column('user_id', sa.String(length=36), nullable=False))
        batch.create_index('ix_notifications_user_id', ['user_id'], unique=False)
        batch.create_foreign_key(
            'fk_notifications_user_id_users',
            'users',
            ['user_id'],
            ['id'],
            ondelete='CASCADE',
        )


def downgrade() -> None:
    with op.batch_alter_table('notifications') as batch:
        batch.drop_constraint('fk_notifications_user_id_users', type_='foreignkey')
        batch.drop_index('ix_notifications_user_id')
        batch.drop_column('user_id')