"""customer 360: code, level, tags, owner, parent, contract, contacts

Revision ID: d3e4f5a6b7c8
Revises: d1e2f3a4b5c6
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "d3e4f5a6b7c8"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customers", sa.Column("code", sa.String(20), nullable=True))
    op.add_column("customers", sa.Column("address", sa.String(300), nullable=True))
    op.add_column("customers", sa.Column("level", sa.String(16), server_default="NORMAL", nullable=True))
    op.add_column("customers", sa.Column("tags", sa.JSON(), nullable=True))
    op.add_column("customers", sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("customers", sa.Column("parent_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True))
    op.add_column("customers", sa.Column("contract_no", sa.String(100), nullable=True))
    op.add_column("customers", sa.Column("service_start", sa.Date(), nullable=True))
    op.add_column("customers", sa.Column("service_end", sa.Date(), nullable=True))
    op.add_column("customers", sa.Column("sla_response_hours", sa.Integer(), nullable=True))
    op.add_column("customers", sa.Column("sla_resolve_hours", sa.Integer(), nullable=True))
    op.execute("UPDATE customers SET code = 'KH-' || lpad(id::text, 4, '0') WHERE code IS NULL")
    op.create_index("ix_customers_code", "customers", ["code"], unique=True)

    op.create_table(
        "customer_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20)),
        sa.Column("email", sa.String(200)),
        sa.Column("title", sa.String(100)),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("remark", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_customer_contacts_customer_id", "customer_contacts", ["customer_id"])
    op.create_index("ix_customer_contacts_phone", "customer_contacts", ["phone"])


def downgrade():
    op.drop_table("customer_contacts")
    op.drop_index("ix_customers_code", table_name="customers")
    for col in ("sla_resolve_hours", "sla_response_hours", "service_end", "service_start",
                "contract_no", "parent_id", "owner_id", "tags", "level", "address", "code"):
        op.drop_column("customers", col)
