"""merge multiple heads

Revision ID: 7b50a2f4dd41
Revises: 18df3b2f5c5e, b225507548a8
Create Date: 2025-11-06 06:40:50.727177

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7b50a2f4dd41'
down_revision = ('18df3b2f5c5e', 'b225507548a8')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
