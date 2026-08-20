"""change parse_pointer from text to json

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-18 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 先将已有 text 数据转为 JSON 格式再改列类型
    op.execute("""
        ALTER TABLE scripts
        ALTER COLUMN parse_pointer
        TYPE jsonb
        USING CASE
            WHEN parse_pointer IS NULL THEN NULL
            WHEN parse_pointer ~ '^\s*[\[{]' THEN parse_pointer::jsonb
            ELSE to_jsonb(parse_pointer)
        END
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE scripts
        ALTER COLUMN parse_pointer
        TYPE text
        USING parse_pointer::text
    """)
