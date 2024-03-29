"""adds need service to reservation

Revision ID: cd0013085e1a
Revises: 58b6e4cd7157
Create Date: 2024-01-26 21:55:05.456997

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cd0013085e1a'
down_revision: Union[str, None] = '58b6e4cd7157'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('reservations', sa.Column('need_service', sa.Boolean(), nullable=False,server_default='False'))
    op.alter_column('reservations', 'user',
               existing_type=sa.INTEGER(),
               nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('reservations', 'user',
               existing_type=sa.INTEGER(),
               nullable=False)
    op.drop_column('reservations', 'need_service')
    # ### end Alembic commands ###
