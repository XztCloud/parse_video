"""add video category/type_summary and shot_features

Revision ID: a1b2c3d4e5f6
Revises: b2c1d3e4f5a6
Create Date: 2026-08-18 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'b2c1d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('videos', sa.Column('category', sa.String(length=64), nullable=True, comment='视频类型（对应前端 tagPresets 类型名）'))
    op.add_column('videos', sa.Column('type_summary', sa.Text(), nullable=True, comment='视频一句话总结'))
    op.add_column('script_segments', sa.Column('shot_features', sa.JSON(), nullable=True, comment='镜头特征标签列表，如 特写/慢动作/全景'))


def downgrade() -> None:
    op.drop_column('script_segments', 'shot_features')
    op.drop_column('videos', 'type_summary')
    op.drop_column('videos', 'category')
