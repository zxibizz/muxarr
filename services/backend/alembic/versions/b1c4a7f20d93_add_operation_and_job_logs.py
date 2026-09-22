"""add operation and job logs

Revision ID: b1c4a7f20d93
Revises: e59efe828ee8
Create Date: 2026-09-22 18:40:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b1c4a7f20d93'
down_revision: str | None = 'e59efe828ee8'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'operations', sa.Column('log', sa.Text(), server_default='[]', nullable=False)
    )
    op.add_column('jobs', sa.Column('log', sa.Text(), server_default='[]', nullable=False))


def downgrade() -> None:
    op.drop_column('jobs', 'log')
    op.drop_column('operations', 'log')
