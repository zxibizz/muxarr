"""add arr context and worker health checks

Revision ID: 4a8e2c6b9d15
Revises: 337991e15296
Create Date: 2026-09-24 23:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = '4a8e2c6b9d15'
down_revision: str | None = '337991e15296'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('operations', sa.Column('arr', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('arr', sa.Text(), nullable=True))
    op.add_column(
        'worker_state', sa.Column('checks', sa.Text(), server_default='[]', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('worker_state', 'checks')
    op.drop_column('jobs', 'arr')
    op.drop_column('operations', 'arr')
