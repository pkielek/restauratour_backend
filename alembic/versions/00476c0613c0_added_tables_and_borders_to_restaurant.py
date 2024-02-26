"""added tables and borders to restaurant

Revision ID: 00476c0613c0
Revises: e6ee7fa68791
Create Date: 2023-12-25 18:55:30.213422

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '00476c0613c0'
down_revision: Union[str, None] = 'e6ee7fa68791'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('restaurant_borders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('restaurant_id', sa.Integer(), nullable=False),
    sa.Column('left', sa.Integer(), nullable=False),
    sa.Column('top', sa.Integer(), nullable=False),
    sa.Column('is_horizontal', sa.Boolean(), nullable=False),
    sa.Column('length', sa.Integer(), nullable=False),
    sa.Column('type', sa.Enum('window', 'door', 'wall', name='restaurantbordertype'), nullable=True),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_restaurant_borders_id'), 'restaurant_borders', ['id'], unique=False)
    op.create_table('restaurant_tables',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('real_id', sa.Integer(), nullable=False),
    sa.Column('restaurant_id', sa.Integer(), nullable=False),
    sa.Column('left', sa.Integer(), nullable=False),
    sa.Column('top', sa.Integer(), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('seats_top', sa.Integer(), nullable=False),
    sa.Column('seats_left', sa.Integer(), nullable=False),
    sa.Column('seats_right', sa.Integer(), nullable=False),
    sa.Column('seats_bottom', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['restaurant_id'], ['restaurants.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_restaurant_tables_id'), 'restaurant_tables', ['id'], unique=False)
    op.add_column('restaurants', sa.Column('plan_precision', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('restaurants', 'plan_precision')
    op.drop_index(op.f('ix_restaurant_tables_id'), table_name='restaurant_tables')
    op.drop_table('restaurant_tables')
    op.drop_index(op.f('ix_restaurant_borders_id'), table_name='restaurant_borders')
    op.drop_table('restaurant_borders')
    # ### end Alembic commands ###