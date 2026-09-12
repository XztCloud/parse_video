"""add new status

Revision ID: be8282e0f046
Revises: e8cb23ac5dac
Create Date: 2026-08-22 11:41:24.077505

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'be8282e0f046'
down_revision: Union[str, None] = 'e8cb23ac5dac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 定义完整的旧 Enum 类型（包含 17 个状态）
old_clone_status = postgresql.ENUM(
    'PENDING', 'PLOT', 'PLOT_DONE', 'VOICE', 'VOICE_DONE', 
    'SEGMENTS', 'SEGMENTS_DONE', 'IMAGE', 'IMAGE_DONE', 
    'FRAME', 'FRAME_DONE', 'SEGMENT_VIDEO', 'SEGMENT_VIDEO_DONE', 
    'MERGE_VIDEO', 'DONE', 'FAILED', 
    name='clonestatus'
)

# 定义精简后的新 CloneStatus Enum 类型
new_clone_status = postgresql.ENUM(
    'PENDING', 'PLOT', 'PLOT_DONE', 'SEGMENTS', 'SEGMENTS_DONE', 'FAILED', 
    name='clonestatus_new'
)

# 定义全新的 GenerateFlowStatus Enum 类型
generate_flow_status_enum = postgresql.ENUM(
    'PENDING', 'VOICE', 'VOICE_DONE', 'IMAGE', 'IMAGE_DONE', 
    'FRAME', 'FRAME_DONE', 'SEGMENT_VIDEO', 'SEGMENT_VIDEO_DONE', 
    'MERGE_VIDEO', 'MERGE_VIDEO_DONE', 'FAILED', 
    name='generateflowstatus'
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 创建全新的 Enum 类型
    new_clone_status.create(bind)
    generate_flow_status_enum.create(bind)

    # 2. 在 clone_scripts 表中新增两个字段
    op.add_column('clone_scripts', sa.Column('generate_flow_status', generate_flow_status_enum, server_default='PENDING', nullable=False))
    op.add_column('clone_scripts', sa.Column('generate_flow_progress', sa.Integer(), server_default='0', nullable=False))

    # 3. 创建临时新列 clone_status_new 用于承接清洗后的 clone_status 数据
    op.add_column('clone_scripts', sa.Column('clone_status_new', new_clone_status, nullable=True))

    # 4. 数据迁移：将属于生成流的状态拆分并填充到 generate_flow_status 中
    # 场景 A: 原状态属于生成阶段（VOICE, IMAGE, FRAME, SEGMENT_VIDEO, MERGE_VIDEO 系列）
    op.execute("""
        UPDATE clone_scripts 
        SET generate_flow_status = clone_status::text::generateflowstatus,
            clone_status_new = 'SEGMENTS_DONE'::clonestatus_new
        WHERE clone_status::text IN (
            'VOICE', 'VOICE_DONE', 'IMAGE', 'IMAGE_DONE', 
            'FRAME', 'FRAME_DONE', 'SEGMENT_VIDEO', 'SEGMENT_VIDEO_DONE', 'MERGE_VIDEO'
        )
    """)

    # 场景 B: 原状态为 DONE（表示整体已完成，映射 generate_flow_status 为 MERGE_VIDEO_DONE）
    op.execute("""
        UPDATE clone_scripts 
        SET generate_flow_status = 'MERGE_VIDEO_DONE'::generateflowstatus,
            clone_status_new = 'SEGMENTS_DONE'::clonestatus_new
        WHERE clone_status::text = 'DONE'
    """)

    # 场景 C: 原状态依然在新的 CloneStatus 范围内（PENDING, PLOT, PLOT_DONE, SEGMENTS, SEGMENTS_DONE, FAILED）
    op.execute("""
        UPDATE clone_scripts 
        SET clone_status_new = clone_status::text::clonestatus_new
        WHERE clone_status_new IS NULL
    """)

    # 5. 删除旧 clone_status 列并将 clone_status_new 改名为 clone_status
    op.drop_column('clone_scripts', 'clone_status')
    op.alter_column('clone_scripts', 'clone_status_new', new_column_name='clone_status', nullable=False, server_default='PENDING')

    # 6. 清理旧数据库 Enum 并将 clonestatus_new 重命名为 clonestatus
    old_clone_status.drop(bind)
    op.execute("ALTER TYPE clonestatus_new RENAME TO clonestatus")
    
    


def downgrade() -> None:
    bind = op.get_bind()

    # 1. 重新创建旧系统的 17 状态 Enum
    old_clone_status.create(bind)

    # 2. 创建临时列接收还原数据
    op.add_column('clone_scripts', sa.Column('clone_status_old', old_clone_status, nullable=True))

    # 3. 将数据合并回单一的 clone_status
    # 如果 generate_flow_status 不为 PENDING，优先取 generate_flow_status 的状态值
    op.execute("""
        UPDATE clone_scripts 
        SET clone_status_old = CASE 
            WHEN generate_flow_status::text = 'MERGE_VIDEO_DONE' THEN 'DONE'::clonestatus
            WHEN generate_flow_status::text != 'PENDING' THEN generate_flow_status::text::clonestatus
            ELSE clone_status::text::clonestatus
        END
    """)

    # 4. 删除新字段并复原原 clone_status 字段
    op.drop_column('clone_scripts', 'clone_status')
    op.alter_column('clone_scripts', 'clone_status_old', new_column_name='clone_status', nullable=False, server_default='PENDING')

    op.drop_column('clone_scripts', 'generate_flow_progress')
    op.drop_column('clone_scripts', 'generate_flow_status')

    # 5. 清理新创建的 Enum 类型
    generate_flow_status_enum.drop(bind)
    new_clone_status.drop(bind)
