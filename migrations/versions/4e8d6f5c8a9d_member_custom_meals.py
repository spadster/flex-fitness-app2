"""Add member custom meals tables

Revision ID: 4e8d6f5c8a9d
Revises: 18df3b2f5c5e
Create Date: 2025-11-06 08:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4e8d6f5c8a9d'
down_revision = '18df3b2f5c5e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'member_meal',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('meal_slot', sa.String(length=20), nullable=False, server_default=sa.text("'meal1'")),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_member_meal_user_slot', 'member_meal', ['user_id', 'meal_slot'])

    op.create_table(
        'member_meal_ingredient',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('meal_id', sa.Integer(), sa.ForeignKey('member_meal.id', ondelete='CASCADE'), nullable=False),
        sa.Column('food_id', sa.Integer(), sa.ForeignKey('food.id', ondelete='CASCADE'), nullable=False),
        sa.Column('quantity_value', sa.Float(), nullable=True),
        sa.Column('quantity_unit', sa.String(length=50), nullable=True),
        sa.Column('quantity_grams', sa.Float(), nullable=False),
        sa.Column('volume_ml', sa.Float(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_member_meal_ingredient_meal_id', 'member_meal_ingredient', ['meal_id'])


def downgrade():
    op.drop_index('ix_member_meal_ingredient_meal_id', table_name='member_meal_ingredient')
    op.drop_table('member_meal_ingredient')
    op.drop_index('ix_member_meal_user_slot', table_name='member_meal')
    op.drop_table('member_meal')
