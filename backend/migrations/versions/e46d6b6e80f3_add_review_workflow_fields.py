"""add review workflow fields

Revision ID: e46d6b6e80f3
Revises: e3da2c5d9027
Create Date: 2026-03-17 09:37:35.676998

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = 'e46d6b6e80f3'
down_revision: Union[str, Sequence[str], None] = 'e3da2c5d9027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.add_column('incident_reports', sa.Column('status', sa.String(), nullable=False, server_default='submitted'))
    op.add_column('incident_reports', sa.Column('review_note', sa.Text(), nullable=True))
    op.add_column('incident_reports', sa.Column('reviewed_by', sa.String(), nullable=True))
    op.add_column('incident_reports', sa.Column('reviewed_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('incident_reports', 'reviewed_at')
    op.drop_column('incident_reports', 'reviewed_by')
    op.drop_column('incident_reports', 'review_note')
    op.drop_column('incident_reports', 'status')