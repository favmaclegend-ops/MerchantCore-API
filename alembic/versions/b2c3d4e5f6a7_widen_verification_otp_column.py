"""widen verification_otp column from VARCHAR(6) to VARCHAR(100)

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-26 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('users', 'verification_otp', type_=sa.String(100))


def downgrade() -> None:
    op.alter_column('users', 'verification_otp', type_=sa.String(6))
