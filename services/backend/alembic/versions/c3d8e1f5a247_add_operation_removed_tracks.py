"""add operation removed tracks

Revision ID: c3d8e1f5a247
Revises: b1c4a7f20d93
Create Date: 2026-09-23 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c3d8e1f5a247'
down_revision: str | None = 'b1c4a7f20d93'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'operations',
        sa.Column('removed_tracks', sa.Text(), server_default='[]', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('operations', 'removed_tracks')
