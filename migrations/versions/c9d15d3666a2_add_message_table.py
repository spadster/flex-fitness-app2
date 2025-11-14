"""Add messaging table for trainer-to-client communication.

Revision ID: c9d15d3666a2
Revises: a6f3f9f2d9b1
Create Date: 2025-11-11 19:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c9d15d3666a2'
down_revision = 'a6f3f9f2d9b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'message',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('trainer_id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['trainer_id'], ['user.id']),
        sa.ForeignKeyConstraint(['client_id'], ['user.id']),
    )


def downgrade():
    op.drop_table('message')
