"""add novels table and modify clone_scripts

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-20
"""
from typing import Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 创建 novels 表
    op.create_table(
        'novels',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False, comment='小说标题'),
        sa.Column('file_path', sa.Text(), nullable=False, comment='novel file path on disk'),
        sa.Column('raw_content', sa.Text(), nullable=True, comment='full novel text'),
        sa.Column('chapter_count', sa.Integer(), nullable=True, comment='detected chapter count'),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='PENDING', comment='PENDING/PROCESSING/DONE/FAILED'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('progress', sa.Integer(), nullable=True, comment='处理进度 0-100'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_novels_id'), 'novels', ['id'], unique=False)

    # 2. 修改 clone_scripts 表
    # 2.1 添加 novel_id 列（外键引用 novels 表）
    op.add_column('clone_scripts', sa.Column('novel_id', sa.Integer(), nullable=True, comment='FK to novels table for NOVEL source_type'))
    op.create_foreign_key('fk_clone_scripts_novel_id', 'clone_scripts', 'novels', ['novel_id'], ['id'], ondelete='SET NULL')

    # 2.2 将 script_id 改为 nullable（支持小说来源）
    # 注意：这里使用 ALTER COLUMN 来修改现有列的 nullable 属性
    op.alter_column('clone_scripts', 'script_id', nullable=True)


def downgrade() -> None:
    # 1. 恢复 clone_scripts.script_id 为 NOT NULL（需要先确保所有 novel_id 为 NULL 的记录都被删除或处理）
    # 注意：如果存在 novel_id 不为 NULL 的记录，需要先处理
    op.alter_column('clone_scripts', 'script_id', nullable=False)

    # 2. 删除 clone_scripts.novel_id 列
    op.drop_constraint('fk_clone_scripts_novel_id', 'clone_scripts', type_='foreignkey')
    op.drop_column('clone_scripts', 'novel_id')

    # 3. 删除 novels 表
    op.drop_index(op.f('ix_novels_id'), table_name='novels')
    op.drop_table('novels')
