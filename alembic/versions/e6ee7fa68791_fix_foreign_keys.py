"""fix foreign keys

Revision ID: e6ee7fa68791
Revises: a265ed8fba6a
Create Date: 2023-12-08 18:27:35.646942

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6ee7fa68791'
down_revision: Union[str, None] = 'a265ed8fba6a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('restaurant_flag_settings_flag_id_fkey', 'restaurant_flag_settings', type_='foreignkey')
    op.create_foreign_key(None, 'restaurant_flag_settings', 'restaurant_flags', ['flag_id'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'restaurant_flag_settings', type_='foreignkey')
    op.create_foreign_key('restaurant_flag_settings_flag_id_fkey', 'restaurant_flag_settings', 'restaurants', ['flag_id'], ['id'])
    # ### end Alembic commands ###