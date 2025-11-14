"""Add read_at flag to message records.

Revision ID: 8730b01a3e26
Revises: 272b01040d23
Create Date: 2025-11-11 21:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8730b01a3e26'
down_revision = '272b01040d23'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('message', sa.Column('read_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('message', 'read_at')
