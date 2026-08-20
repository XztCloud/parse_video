"""add source_type to clone_scripts

Revision ID: b2c1d3e4f5a6
Revises: 6be585a63cee
Create Date: 2026-08-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c1d3e4f5a6'
down_revision: Union[str, None] = '6be585a63cee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 工作台来源：CLONE=复刻剧本 / ORIGINAL=原片直转渲染
    op.add_column(
        'clone_scripts',
        sa.Column('source_type', sa.String(length=16), nullable=False, server_default='CLONE'),
    )


def downgrade() -> None:
    op.drop_column('clone_scripts', 'source_type')