"""followers

Revision ID: 8907431167e2
Revises: 3db9faaa854b
Create Date: 2021-07-15 18:25:35.380898

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8907431167e2'
down_revision = '3db9faaa854b'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('association')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('association',
    sa.Column('user_id', sa.INTEGER(), nullable=True),
    sa.Column('friend_id', sa.INTEGER(), nullable=True),
    sa.ForeignKeyConstraint(['friend_id'], ['user.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], )
    )
    # ### end Alembic commands ###
