"""Add trainer meal planning and custom macro targets

Revision ID: 18df3b2f5c5e
Revises: 8db8ab9d5b76
Create Date: 2025-11-06 06:05:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '18df3b2f5c5e'
down_revision = '8db8ab9d5b76'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('custom_calorie_target', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('custom_protein_target_g', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('custom_carb_target_g', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('custom_fat_target_g', sa.Float(), nullable=True))

    op.create_table(
        'trainer_meal',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('trainer_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=False),
        sa.Column('member_id', sa.Integer(), sa.ForeignKey('user.id', ondelete='CASCADE'), nullable=True),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('meal_slot', sa.String(length=20), nullable=False, default='meal1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_trainer_meal_member_slot', 'trainer_meal', ['trainer_id', 'member_id', 'meal_slot'])

    op.create_table(
        'trainer_meal_ingredient',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('meal_id', sa.Integer(), sa.ForeignKey('trainer_meal.id', ondelete='CASCADE'), nullable=False),
        sa.Column('food_id', sa.Integer(), sa.ForeignKey('food.id', ondelete='CASCADE'), nullable=False),
        sa.Column('quantity_value', sa.Float(), nullable=True),
        sa.Column('quantity_unit', sa.String(length=50), nullable=True),
        sa.Column('quantity_grams', sa.Float(), nullable=False),
        sa.Column('volume_ml', sa.Float(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=False, default=0),
        sa.Column('notes', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('ix_trainer_meal_ingredient_meal_id', 'trainer_meal_ingredient', ['meal_id'])


def downgrade():
    op.drop_index('ix_trainer_meal_ingredient_meal_id', table_name='trainer_meal_ingredient')
    op.drop_table('trainer_meal_ingredient')
    op.drop_index('ix_trainer_meal_member_slot', table_name='trainer_meal')
    op.drop_table('trainer_meal')

    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('custom_fat_target_g')
        batch_op.drop_column('custom_carb_target_g')
        batch_op.drop_column('custom_protein_target_g')
        batch_op.drop_column('custom_calorie_target')
