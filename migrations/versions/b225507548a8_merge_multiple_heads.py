"""merge multiple heads

Revision ID: b225507548a8
Revises: 7f3646184ca2, 8db8ab9d5b76
Create Date: 2025-11-06 05:30:01.381017

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b225507548a8'
down_revision = ('7f3646184ca2', '8db8ab9d5b76')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
