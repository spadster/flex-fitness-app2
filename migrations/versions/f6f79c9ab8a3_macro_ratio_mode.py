"""Add macro target mode and ratio columns

Revision ID: f6f79c9ab8a3
Revises: ed9915b867c1
Create Date: 2025-11-10 20:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f6f79c9ab8a3'
down_revision = 'ed9915b867c1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('macro_target_mode', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('macro_ratio_protein', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('macro_ratio_carbs', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('macro_ratio_fats', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('macro_ratio_fats')
        batch_op.drop_column('macro_ratio_carbs')
        batch_op.drop_column('macro_ratio_protein')
        batch_op.drop_column('macro_target_mode')

