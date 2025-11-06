"""merge multiple heads

Revision ID: ed9915b867c1
Revises: 4e8d6f5c8a9d, 7b50a2f4dd41
Create Date: 2025-11-06 08:07:53.468244

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ed9915b867c1'
down_revision = ('4e8d6f5c8a9d', '7b50a2f4dd41')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
