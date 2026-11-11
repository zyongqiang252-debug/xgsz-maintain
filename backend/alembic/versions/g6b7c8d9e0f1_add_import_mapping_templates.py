"""import mapping templates

Revision ID: g6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "g6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "import_mapping_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("scene", sa.String(40), nullable=False, server_default="work_order_excel"),
        sa.Column("header_signature", sa.String(500), nullable=False),
        sa.Column("headers", sa.JSON()),
        sa.Column("mapping", sa.JSON()),
        sa.Column("created_by", sa.Integer()),
        sa.Column("creator_name", sa.String(100)),
        sa.Column("use_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_import_mapping_templates_created_by", "import_mapping_templates", ["created_by"])
    op.create_index("ix_import_mapping_templates_sig", "import_mapping_templates", ["scene", "header_signature"])


def downgrade():
    op.drop_index("ix_import_mapping_templates_sig", table_name="import_mapping_templates")
    op.drop_index("ix_import_mapping_templates_created_by", table_name="import_mapping_templates")
    op.drop_table("import_mapping_templates")
