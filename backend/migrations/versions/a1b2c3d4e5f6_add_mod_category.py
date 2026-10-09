"""add mods.category

Revision ID: a1b2c3d4e5f6
Revises: 9d2393a22114
Create Date: 2026-10-09

按 Workshop 标签为 Mod 增加主类型(category),并用现有 tags 回填。
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "9d2393a22114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mods", sa.Column("category", sa.String(length=32),
                                    nullable=False, server_default="Other"))
    op.create_index("ix_mods_category", "mods", ["category"])

    from app.services.categories import derive_category

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT workshop_id, tags FROM mods")).fetchall()
    for wid, tags in rows:
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (ValueError, TypeError):
                tags = []
        conn.execute(sa.text("UPDATE mods SET category = :c WHERE workshop_id = :w"),
                     {"c": derive_category(tags), "w": wid})


def downgrade() -> None:
    op.drop_index("ix_mods_category", table_name="mods")
    op.drop_column("mods", "category")