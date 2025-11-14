"""Add theme mode preference to users

Revision ID: a6f3f9f2d9b1
Revises: f6f79c9ab8a3
Create Date: 2025-11-10 22:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a6f3f9f2d9b1'
down_revision = 'f6f79c9ab8a3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('theme_mode', sa.String(length=20), nullable=True))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('theme_mode')

