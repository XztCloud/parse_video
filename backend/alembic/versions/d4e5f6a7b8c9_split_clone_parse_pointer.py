"""split clone_parse_pointer into focus + plot

Revision ID: d4e5f6a7b8c9
Revises: b2c3d4e5f6a7
Create Date: 2026-08-19
"""
from typing import Union
import json
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. 新增列
    op.add_column('clone_scripts', sa.Column('clone_parse_script', sa.JSON, nullable=True, comment='解析剧本脚本 CloneAnalysisPlot JSON'))

    # 2. 数据迁移：从 clone_parse_pointer 中提取 plot_script 写入 clone_parse_script
    bind = op.get_bind()
    result = bind.execute(text("SELECT id, clone_parse_pointer FROM clone_scripts WHERE clone_parse_pointer IS NOT NULL"))
    for row in result:
        cs_id = row[0]
        ptr = row[1]
        if isinstance(ptr, str):
            ptr = json.loads(ptr)
        if not isinstance(ptr, dict):
            continue
        plot_data = {"plot_script": ptr.get("plot_script", [])}
        # 从 focus 中移除 plot_script（如果有的话）
        focus_data = {k: v for k, v in ptr.items() if k != "plot_script"}
        bind.execute(
            text("UPDATE clone_scripts SET clone_parse_pointer = :focus, clone_parse_script = :plot WHERE id = :id"),
            {"focus": json.dumps(focus_data, ensure_ascii=False), "plot": json.dumps(plot_data, ensure_ascii=False), "id": cs_id}
        )


def downgrade() -> None:
    # 合并回 clone_parse_pointer
    bind = op.get_bind()
    result = bind.execute(text("SELECT id, clone_parse_pointer, clone_parse_script FROM clone_scripts WHERE clone_parse_script IS NOT NULL"))
    for row in result:
        cs_id = row[0]
        ptr = row[1] if isinstance(row[1], dict) else json.loads(row[1]) if row[1] else {}
        script = row[2] if isinstance(row[2], dict) else json.loads(row[2]) if row[2] else {}
        ptr["plot_script"] = script.get("plot_script", [])
        bind.execute(
            text("UPDATE clone_scripts SET clone_parse_pointer = :ptr WHERE id = :id"),
            {"ptr": json.dumps(ptr, ensure_ascii=False), "id": cs_id}
        )
    op.drop_column('clone_scripts', 'clone_parse_script')
