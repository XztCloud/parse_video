"""add asset ownership (videos/novels.user_id) and cascade novel deletions

Revision ID: f0e1d2c3b4a5
Revises: be8282e0f046
Create Date: 2026-09-12
"""
from typing import Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f0e1d2c3b4a5'
down_revision: Union[str, None] = 'be8282e0f046'
branch_labels = None
depends_on = None

# 现有资产统一归属的管理员账号
ADMIN_EMAIL = '18017283108@qq.com'


def _novel_id_fk_name() -> str:
    """按列名查出 clone_scripts.novel_id 的真实外键约束名（不硬编码）。"""
    insp = sa.inspect(op.get_bind())
    for fk in insp.get_foreign_keys('clone_scripts'):
        if fk.get('constrained_columns') == ['novel_id']:
            return fk['name']
    return 'fk_clone_scripts_novel_id'


def upgrade() -> None:
    # 1. videos / novels 增加归属用户列。
    #    保持 nullable：历史数据若回填不到（管理员账号缺失）也不会让 upgrade 失败；
    #    未归属（NULL）的行仅超管可见。
    op.add_column('videos', sa.Column(
        'user_id', postgresql.UUID(as_uuid=True), nullable=True,
        comment='归属用户；删除用户时级联删除其视频'))
    op.create_foreign_key('fk_videos_user_id', 'videos', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_videos_user_id', 'videos', ['user_id'], unique=False)

    op.add_column('novels', sa.Column(
        'user_id', postgresql.UUID(as_uuid=True), nullable=True,
        comment='归属用户；删除用户时级联删除其小说与剧本章节'))
    op.create_foreign_key('fk_novels_user_id', 'novels', 'users', ['user_id'], ['id'], ondelete='CASCADE')
    op.create_index('ix_novels_user_id', 'novels', ['user_id'], unique=False)

    # 2. 现有资产统一归属管理员（优先按配置邮箱，兜底取任一超管）
    for table in ('videos', 'novels'):
        op.execute(f"""
            UPDATE {table}
            SET user_id = COALESCE(
                (SELECT id FROM users WHERE email = '{ADMIN_EMAIL}'),
                (SELECT id FROM users WHERE is_superuser IS TRUE ORDER BY created_at LIMIT 1)
            )
            WHERE user_id IS NULL
        """)

    # 3. clone_scripts.novel_id 外键由 SET NULL 改为 CASCADE。
    #    否则删除小说（进而删除其归属用户）时只会把 novel_id 置空，留下孤儿复刻脚本。
    fk_name = _novel_id_fk_name()
    op.drop_constraint(fk_name, 'clone_scripts', type_='foreignkey')
    op.create_foreign_key(fk_name, 'clone_scripts', 'novels', ['novel_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    # 3. clone_scripts.novel_id 恢复为 SET NULL
    fk_name = _novel_id_fk_name()
    op.drop_constraint(fk_name, 'clone_scripts', type_='foreignkey')
    op.create_foreign_key(fk_name, 'clone_scripts', 'novels', ['novel_id'], ['id'], ondelete='SET NULL')

    # 1/2. 回滚归属列（回填的数据一并丢失）
    op.drop_index('ix_novels_user_id', table_name='novels')
    op.drop_constraint('fk_novels_user_id', 'novels', type_='foreignkey')
    op.drop_column('novels', 'user_id')

    op.drop_index('ix_videos_user_id', table_name='videos')
    op.drop_constraint('fk_videos_user_id', 'videos', type_='foreignkey')
    op.drop_column('videos', 'user_id')
