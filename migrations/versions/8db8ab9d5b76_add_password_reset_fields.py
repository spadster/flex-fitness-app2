"""add password reset token columns

Revision ID: 8db8ab9d5b76
Revises: 23fa200194ab
Create Date: 2025-11-05 20:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8db8ab9d5b76'
down_revision = '23fa200194ab'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password_reset_token', sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column('password_reset_sent_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('password_reset_sent_at')
        batch_op.drop_column('password_reset_token')
