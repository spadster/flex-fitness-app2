"""merge multiple heads

Revision ID: 7f3646184ca2
Revises: 23fa200194ab, bb8574fda196
Create Date: 2025-11-06 05:13:39.810126

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7f3646184ca2'
down_revision = ('23fa200194ab', 'bb8574fda196')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
