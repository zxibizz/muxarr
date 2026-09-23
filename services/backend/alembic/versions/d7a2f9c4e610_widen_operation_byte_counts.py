"""widen operation byte counts

Revision ID: d7a2f9c4e610
Revises: c3d8e1f5a247
Create Date: 2026-09-23 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd7a2f9c4e610'
down_revision: str | None = 'c3d8e1f5a247'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUMNS = ('source_bytes', 'output_bytes')


def upgrade() -> None:
    # Postgres INTEGER is 32-bit; SQLite's is already 64-bit, so there it only rebuilds.
    with op.batch_alter_table('operations', schema=None) as batch_op:
        for column in _COLUMNS:
            batch_op.alter_column(
                column, existing_type=sa.Integer(), type_=sa.BigInteger(), existing_nullable=True
            )


def downgrade() -> None:
    with op.batch_alter_table('operations', schema=None) as batch_op:
        for column in _COLUMNS:
            batch_op.alter_column(
                column, existing_type=sa.BigInteger(), type_=sa.Integer(), existing_nullable=True
            )
