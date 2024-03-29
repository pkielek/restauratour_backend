"""Added temporary column to RestaurantHours

Revision ID: 32c35c52c9c0
Revises: c2b0dc52cdec
Create Date: 2024-01-06 00:27:10.421931

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '32c35c52c9c0'
down_revision: Union[str, None] = 'c2b0dc52cdec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('restaurant_opening_hours', sa.Column('temporary', sa.Boolean(), nullable=True))
    op.alter_column('restaurant_opening_hours', 'open_time',
               existing_type=postgresql.TIME(),
               nullable=True)
    op.alter_column('restaurant_opening_hours', 'close_time',
               existing_type=postgresql.TIME(),
               nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('restaurant_opening_hours', 'close_time',
               existing_type=postgresql.TIME(),
               nullable=False)
    op.alter_column('restaurant_opening_hours', 'open_time',
               existing_type=postgresql.TIME(),
               nullable=False)
    op.drop_column('restaurant_opening_hours', 'temporary')
    # ### end Alembic commands ###
