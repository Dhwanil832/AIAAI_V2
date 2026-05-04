"""add vision_threads table

Revision ID: add_vision_thread
Revises: 44800dc994c8
Create Date: 2026-04-16

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_vision_thread'
down_revision = '44800dc994c8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'vision_threads',

        sa.Column('id', sa.Integer(), primary_key=True),

        sa.Column('report_id', sa.Integer(),
                  sa.ForeignKey('incident_reports.id'), nullable=True),

        sa.Column('unfinished_report_id', sa.Integer(),
                  sa.ForeignKey('unfinished_reports.id'), nullable=True),

        sa.Column('trigger_context', sa.String(), nullable=False),

        sa.Column('triggered_by_user_id', sa.Integer(),
                  sa.ForeignKey('users.id'), nullable=False),

        sa.Column('image_paths', sa.JSON(), nullable=True),

        sa.Column('quality_ok', sa.Boolean(), nullable=True),
        sa.Column('quality_reason', sa.String(), nullable=True),

        sa.Column('full_observations', sa.JSON(), nullable=True),

        sa.Column('priority_observation', sa.JSON(), nullable=True),

        sa.Column('conversation', sa.JSON(), nullable=True),

        sa.Column('resolution', sa.String(), nullable=False,
                  server_default='pending'),

        sa.Column('resolution_note', sa.Text(), nullable=True),

        sa.Column('amendments', sa.JSON(), nullable=True),

        sa.Column('secondary_flags', sa.JSON(), nullable=True),

        sa.Column('status', sa.String(), nullable=False,
                  server_default='open'),

        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('vision_threads')