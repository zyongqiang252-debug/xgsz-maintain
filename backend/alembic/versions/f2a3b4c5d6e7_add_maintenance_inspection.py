"""create maintenance_plans / maintenance_records / inspection_templates / inspection_records

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "maintenance_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_name", sa.String(200), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id")),
        sa.Column("device_code", sa.String(50)),
        sa.Column("items", sa.Text()),
        sa.Column("cycle_type", sa.String(16), server_default="DAYS"),
        sa.Column("cycle_value", sa.Integer(), server_default="30"),
        sa.Column("last_done_at", sa.TIMESTAMP()),
        sa.Column("next_due_at", sa.TIMESTAMP()),
        sa.Column("responsible_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("responsible_name", sa.String(100)),
        sa.Column("status", sa.String(16), server_default="ACTIVE"),
        sa.Column("remark", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
    )
    op.create_index("ix_maintenance_plans_device_id", "maintenance_plans", ["device_id"])
    op.create_index("ix_maintenance_plans_device_code", "maintenance_plans", ["device_code"])
    op.create_index("ix_maintenance_plans_next_due_at", "maintenance_plans", ["next_due_at"])
    op.create_index("ix_maintenance_plans_status", "maintenance_plans", ["status"])

    op.create_table(
        "maintenance_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), sa.ForeignKey("maintenance_plans.id")),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id")),
        sa.Column("device_code", sa.String(50)),
        sa.Column("plan_name", sa.String(200)),
        sa.Column("done_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.Column("done_by_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("done_by_name", sa.String(100)),
        sa.Column("result", sa.String(16), server_default="OK"),
        sa.Column("cost", sa.Float(), server_default="0"),
        sa.Column("remark", sa.Text()),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id")),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
    )
    op.create_index("ix_maintenance_records_plan_id", "maintenance_records", ["plan_id"])
    op.create_index("ix_maintenance_records_done_at", "maintenance_records", ["done_at"])

    op.create_table(
        "inspection_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("device_type", sa.String(100)),
        sa.Column("items", JSONB()),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
    )
    op.create_index("ix_inspection_templates_device_type", "inspection_templates", ["device_type"])

    op.create_table(
        "inspection_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("inspection_templates.id")),
        sa.Column("template_name", sa.String(200)),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id")),
        sa.Column("device_code", sa.String(50)),
        sa.Column("inspector_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("inspector_name", sa.String(100)),
        sa.Column("result", sa.String(16), server_default="OK"),
        sa.Column("abnormal_count", sa.Integer(), server_default="0"),
        sa.Column("results", JSONB()),
        sa.Column("remark", sa.Text()),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id")),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
    )
    op.create_index("ix_inspection_records_template_id", "inspection_records", ["template_id"])
    op.create_index("ix_inspection_records_device_id", "inspection_records", ["device_id"])
    op.create_index("ix_inspection_records_device_code", "inspection_records", ["device_code"])
    op.create_index("ix_inspection_records_result", "inspection_records", ["result"])


def downgrade():
    op.drop_table("inspection_records")
    op.drop_table("inspection_templates")
    op.drop_table("maintenance_records")
    op.drop_table("maintenance_plans")
