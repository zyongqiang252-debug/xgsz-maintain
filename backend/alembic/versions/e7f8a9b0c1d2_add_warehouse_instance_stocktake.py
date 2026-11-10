"""add warehouses / part instances(SN) / stocktakes + spare_parts.reserved_quantity

Revision ID: e7f8a9b0c1d2
Revises: c0d1e2f3a4b5
Create Date: 2026-11-10

本次新增（对应「备件库存补控制层」四件事）：
  1. warehouses / warehouse_locations —— 多仓与库位
  2. part_instances                   —— SN 级实物追溯（一物一码）
  3. stocktakes / stocktake_items     —— 盘点单（差异走 ADJUST 流水，不直接改数）
  4. spare_parts.reserved_quantity    —— 审批预占，解决并发超卖

兼容性：只加表/加列，不改不改动既有列；历史备件全部归到种子仓 MAIN。
"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "c0d1e2f3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    # ---------- 1. 仓库 / 库位 ----------
    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("address", sa.String(300)),
        sa.Column("manager_name", sa.String(100)),
        sa.Column("phone", sa.String(50)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("remark", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_warehouses_code", "warehouses", ["code"])

    op.create_table(
        "warehouse_locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("warehouse_id", sa.Integer(),
                  sa.ForeignKey("warehouses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("rack", sa.String(50)),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("remark", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("warehouse_id", "code", name="uq_warehouse_location_code"),
    )
    op.create_index("ix_warehouse_locations_warehouse_id", "warehouse_locations", ["warehouse_id"])

    # ---------- 2. 备件台账加：所属仓库 + 预占 ----------
    op.add_column("spare_parts", sa.Column("warehouse_id", sa.Integer(), nullable=True))
    op.add_column("spare_parts", sa.Column(
        "reserved_quantity", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.create_foreign_key(
        "fk_spare_parts_warehouse_id_warehouses", "spare_parts", "warehouses",
        ["warehouse_id"], ["id"],
    )
    op.create_index("ix_spare_parts_warehouse_id", "spare_parts", ["warehouse_id"])

    # 种子仓：历史备件没有仓，全部归到主仓，否则新建盘点单会扫出"未归仓"
    op.execute(
        "INSERT INTO warehouses (code, name, address, is_active, created_at, updated_at) "
        "VALUES ('MAIN', '主仓', '默认仓库（迁移自动创建）', true, now(), now())"
    )
    op.execute(
        "INSERT INTO warehouse_locations (warehouse_id, code, name, rack, is_active, created_at, updated_at) "
        "SELECT id, 'A-01', '默认库位', 'A', true, now(), now() FROM warehouses WHERE code = 'MAIN'"
    )
    op.execute(
        "UPDATE spare_parts SET warehouse_id = (SELECT id FROM warehouses WHERE code = 'MAIN') "
        "WHERE warehouse_id IS NULL"
    )

    # ---------- 3. 备件实例（SN 追溯） ----------
    op.create_table(
        "part_instances",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("spare_parts.id"), nullable=False),
        sa.Column("part_code", sa.String(50)),
        sa.Column("part_name", sa.String(200)),
        sa.Column("sn", sa.String(100)),
        sa.Column("status", sa.String(16), nullable=False, server_default="IN_STOCK"),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id")),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("warehouse_locations.id")),
        sa.Column("location_text", sa.String(200)),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id")),
        sa.Column("device_code", sa.String(50)),
        sa.Column("gpu_index", sa.Integer()),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id")),
        sa.Column("unit_price", sa.Float(), server_default=sa.text("0")),
        sa.Column("supplier", sa.String(200)),
        sa.Column("warranty_until", sa.DateTime()),
        sa.Column("installed_at", sa.DateTime()),
        sa.Column("removed_at", sa.DateTime()),
        sa.Column("inbound_movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id")),
        sa.Column("outbound_movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id")),
        sa.Column("remark", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_part_instances_part_id", "part_instances", ["part_id"])
    op.create_index("ix_part_instances_part_code", "part_instances", ["part_code"])
    op.create_index("ix_part_instances_sn", "part_instances", ["sn"])
    op.create_index("ix_part_instances_status", "part_instances", ["status"])
    op.create_index("ix_part_instances_device_code", "part_instances", ["device_code"])
    op.create_index("ix_part_instances_warehouse_id", "part_instances", ["warehouse_id"])
    op.create_index("ix_part_instances_location_id", "part_instances", ["location_id"])
    op.create_index("ix_part_instances_work_order_id", "part_instances", ["work_order_id"])

    # ---------- 4. 盘点单 ----------
    op.create_table(
        "stocktakes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("take_no", sa.String(50), nullable=False, unique=True),
        sa.Column("warehouse_id", sa.Integer(), sa.ForeignKey("warehouses.id")),
        sa.Column("warehouse_name", sa.String(200)),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("item_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("counted_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("diff_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("diff_amount", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("created_by_name", sa.String(100)),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("approved_by", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approved_by_name", sa.String(100)),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("remark", sa.Text()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_stocktakes_take_no", "stocktakes", ["take_no"])
    op.create_index("ix_stocktakes_status", "stocktakes", ["status"])
    op.create_index("ix_stocktakes_warehouse_id", "stocktakes", ["warehouse_id"])

    op.create_table(
        "stocktake_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stocktake_id", sa.Integer(),
                  sa.ForeignKey("stocktakes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("spare_parts.id"), nullable=False),
        sa.Column("part_code", sa.String(50)),
        sa.Column("part_name", sa.String(200)),
        sa.Column("unit", sa.String(20)),
        sa.Column("location_text", sa.String(200)),
        sa.Column("system_qty", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("actual_qty", sa.Float()),
        sa.Column("diff_qty", sa.Float()),
        sa.Column("unit_price", sa.Float(), server_default=sa.text("0")),
        sa.Column("diff_amount", sa.Float(), server_default=sa.text("0")),
        sa.Column("reason", sa.String(200)),
        sa.Column("movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_stocktake_items_stocktake_id", "stocktake_items", ["stocktake_id"])
    op.create_index("ix_stocktake_items_part_id", "stocktake_items", ["part_id"])
    op.create_index("ix_stocktake_items_part_code", "stocktake_items", ["part_code"])


def downgrade():
    op.drop_table("stocktake_items")
    op.drop_table("stocktakes")
    op.drop_table("part_instances")
    op.drop_index("ix_spare_parts_warehouse_id", table_name="spare_parts")
    op.drop_constraint("fk_spare_parts_warehouse_id_warehouses", "spare_parts", type_="foreignkey")
    op.drop_column("spare_parts", "reserved_quantity")
    op.drop_column("spare_parts", "warehouse_id")
    op.drop_table("warehouse_locations")
    op.drop_table("warehouses")
