r"""备件库存四项补强自检：仓库库位 / 实例(SN) / 盘点单 / 预占

跑法（在 backend 目录下）：
    .\.venv\Scripts\python.exe ..\tools\verify_spare_stock.py

只验证这四项，不碰真实业务数据：
  - 用 TEST- 前缀造仓库/备件/实例，跑完自动清理；
  - 领用单不带工单号，不会回写任何真实工单的成本。
"""
import os
import sys
import traceback

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.insert(0, BACKEND)
os.chdir(BACKEND)

from fastapi import FastAPI, HTTPException  # noqa: E402

from app.api import (  # noqa: E402
    part_instances as pi_api,
    spare_part_requisitions as rq_api,
    spare_parts as sp_api,
    stocktakes as st_api,
    warehouses as wh_api,
)
from app.core.database import SessionLocal  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.part_instance import PartInstance  # noqa: E402
from app.models.spare_part import SparePart  # noqa: E402
from app.models.spare_part_requisition import SparePartRequisition  # noqa: E402
from app.models.stock_movement import StockMovement  # noqa: E402
from app.models.stocktake import Stocktake, StocktakeItem  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.warehouse import Warehouse, WarehouseLocation  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    if cond:
        PASS.append(name)
        print(f"[PASS] {name} {detail}")
    else:
        FAIL.append(name)
        print(f"[FAIL] {name} {detail}")


def refresh(db, obj):
    db.refresh(obj)
    return obj


def purge_test_data(db):
    """清掉所有 TEST- 前缀的自检数据（顺序照顾外键：先子表，最后父表）"""
    parts = db.query(SparePart).filter(SparePart.part_code.like("TEST-SPARE-%")).all()
    pids = [p.id for p in parts]
    if pids:
        db.query(StocktakeItem).filter(StocktakeItem.part_id.in_(pids)).delete(synchronize_session=False)
        db.query(PartInstance).filter(PartInstance.part_id.in_(pids)).delete(synchronize_session=False)
        db.query(SparePartRequisition).filter(
            SparePartRequisition.part_id.in_(pids)).delete(synchronize_session=False)
        # 流水引用 spare_parts.id，必须在删备件之前删
        db.query(StockMovement).filter(
            StockMovement.part_code.like("TEST-SPARE-%")).delete(synchronize_session=False)
        db.query(SparePart).filter(SparePart.id.in_(pids)).delete(synchronize_session=False)
    db.query(StockMovement).filter(
        StockMovement.part_code.like("TEST-SPARE-%")).delete(synchronize_session=False)
    db.query(Stocktake).filter(Stocktake.remark.like("%自检%")).delete(synchronize_session=False)
    for w in db.query(Warehouse).filter(Warehouse.code.like("TEST-%")).all():
        db.query(WarehouseLocation).filter(
            WarehouseLocation.warehouse_id == w.id).delete(synchronize_session=False)
        db.query(Warehouse).filter(Warehouse.id == w.id).delete(synchronize_session=False)
    db.commit()


def main():
    db = SessionLocal()
    admin = (db.query(User).filter(User.is_active.is_(True))
             .order_by(User.id).first())
    if not admin:
        print("[FATAL] 库里没有可用账号，先初始化数据")
        return 2
    print(f"使用账号：{admin.username} / {admin.real_name}")

    # 上一次跑剩下的自检数据先清掉，保证可重复执行
    purge_test_data(db)

    # ---------- 0. 路由顺序（/requisitions 不能被 /{part_id} 吃掉） ----------
    app = FastAPI()
    app.include_router(rq_api.router, prefix="/api/v1/spare-parts/requisitions")
    app.include_router(sp_api.router, prefix="/api/v1/spare-parts")
    paths = [r.path for r in app.routes]
    req_i = paths.index("/api/v1/spare-parts/requisitions/")
    part_i = paths.index("/api/v1/spare-parts/{part_id}")
    check("领用单路由排在 /{part_id} 之前", req_i < part_i, f"{req_i} < {part_i}")

    wh_id = loc_id = part_id = None
    try:
        # ---------- 1. 仓库 / 库位 ----------
        wh = wh_api.create_warehouse(
            wh_api.WarehouseIn(code="TEST-WH", name="自检仓", manager_name=admin.real_name),
            db=db, current_user=admin)
        wh_id = wh["id"]
        check("新建仓库", wh["code"] == "TEST-WH")

        loc = wh_api.create_location(
            wh_id, wh_api.LocationIn(code="T-01", name="自检库位", rack="T"),
            db=db, current_user=admin)
        loc_id = loc["id"]
        check("新建库位", loc["code"] == "T-01")

        dup = False
        try:
            wh_api.create_location(wh_id, wh_api.LocationIn(code="T-01"), db=db, current_user=admin)
        except HTTPException as e:
            dup = e.status_code == 400
            db.rollback()
        check("同仓库库位编码重复被拦", dup)
        db.rollback()

        # ---------- 2. 备件 + 实例（SN 入库） ----------
        part = SparePart(part_code="TEST-SPARE-001", part_name="自检 GPU 卡",
                         specification="SXM", unit="块", stock_quantity=0,
                         safety_stock=1, unit_price=100.0,
                         warehouse_id=wh_id, reserved_quantity=0)
        db.add(part)
        db.commit()
        db.refresh(part)
        part_id = part.id

        i1 = pi_api.register_instance(pi_api.RegisterIn(
            part_id=part_id, sn="TESTSN0001", warehouse_id=wh_id, location_id=loc_id),
            db=db, current_user=admin)
        pi_api.register_instance(pi_api.RegisterIn(
            part_id=part_id, sn="TESTSN0002", warehouse_id=wh_id, location_id=loc_id),
            db=db, current_user=admin)
        refresh(db, part)
        check("登记实例同时入库", float(part.stock_quantity) == 2,
              f"库存={part.stock_quantity}")
        check("实例状态在库", i1["status"] == "IN_STOCK" and i1["location_text"] == "T-01")

        dup_sn = False
        try:
            pi_api.register_instance(pi_api.RegisterIn(part_id=part_id, sn="TESTSN0001"),
                                     db=db, current_user=admin)
        except HTTPException as e:
            dup_sn = e.status_code == 400
            db.rollback()
        check("同 SN 重复登记被拦", dup_sn)
        db.rollback()

        # ---------- 3. 领用审批：预占 + 超卖拦截 ----------
        r1 = rq_api.create_requisition(
            rq_api.RequisitionIn(part_id=part_id, quantity=2, reason="自检领用"),
            db=db, current_user=admin)
        a1 = rq_api.approve_requisition(r1["id"], db=db, current_user=admin)
        refresh(db, part)
        check("审批通过后预占 2", float(part.reserved_quantity) == 2,
              f"现存={part.stock_quantity} 预占={part.reserved_quantity}")
        check("可用库存=0", a1["available_quantity"] == 0, f"available={a1['available_quantity']}")

        r2 = rq_api.create_requisition(
            rq_api.RequisitionIn(part_id=part_id, quantity=1, reason="自检再来一张"),
            db=db, current_user=admin)
        blocked = False
        try:
            rq_api.approve_requisition(r2["id"], db=db, current_user=admin)
        except HTTPException as e:
            blocked = e.status_code == 400
            msg = e.detail
            db.rollback()
        check("预占后可用不足被拦（防超卖）", blocked, msg if blocked else "")
        db.rollback()

        issue = rq_api.issue_requisition(r1["id"], rq_api.IssueIn(remark="自检出库"),
                                         db=db, current_user=admin)
        refresh(db, part)
        check("出库扣库存", float(part.stock_quantity) == 0, f"现存={part.stock_quantity}")
        check("出库释放预占", float(part.reserved_quantity) == 0, f"预占={part.reserved_quantity}")
        check("出库写了 OUT 流水", issue["movement_id"] is not None)
        mv = db.query(StockMovement).filter(StockMovement.id == issue["movement_id"]).first()
        check("流水 before/after 正确",
              mv is not None and mv.before_qty == 2 and mv.after_qty == 0,
              f"{mv.before_qty}->{mv.after_qty}" if mv else "")

        # 撤销已预占的单要能释放预占
        r3 = rq_api.create_requisition(
            rq_api.RequisitionIn(part_id=part_id, quantity=1, reason="自检撤销"),
            db=db, current_user=admin)
        db.refresh(part)
        part.stock_quantity = 1  # 手工补一个，供预占测试
        db.commit()
        rq_api.approve_requisition(r3["id"], db=db, current_user=admin)
        rq_api.cancel_requisition(r3["id"], db=db, current_user=admin)
        refresh(db, part)
        check("撤销已批准单释放预占", float(part.reserved_quantity) == 0,
              f"预占={part.reserved_quantity}")

        # ---------- 4. 实例装机 / 拆回 ----------
        dev = db.query(Device).order_by(Device.id).first()
        if dev:
            inst = pi_api.install_instance(
                i1["id"], pi_api.InstallIn(device_id=dev.id, gpu_index=0),
                db=db, current_user=admin)
            check("装机后状态=已装机", inst["status"] == "INSTALLED",
                  f"设备={inst['device_code']}")
            refresh(db, part)
            check("未出过库的件装机自动扣 1", float(part.stock_quantity) == 0,
                  f"现存={part.stock_quantity}")
            back = pi_api.return_instance(i1["id"], pi_api.ReturnIn(), db=db, current_user=admin)
            refresh(db, part)
            check("拆回后状态=在库", back["status"] == "IN_STOCK")
            check("拆回库存 +1", float(part.stock_quantity) == 1, f"现存={part.stock_quantity}")
        else:
            print("[SKIP] 库里没有设备，跳过装机/拆回")

        # ---------- 5. 盘点：盘→提交→审批→红冲 ----------
        take = st_api.create_stocktake(
            st_api.CreateIn(keyword="TEST-SPARE-001", remark="自检盘点"),
            db=db, current_user=admin)
        detail = st_api.get_stocktake(take["id"], db=db)
        check("盘点单条目数=1", len(detail["items"]) == 1, f"items={len(detail['items'])}")
        item = detail["items"][0]
        check("账面数量快照", item["system_qty"] == 1, f"system={item['system_qty']}")

        st_api.count_stocktake(take["id"], st_api.CountIn(items=[
            st_api.CountItem(item_id=item["id"], actual_qty=3, reason="自检盘盈"),
        ]), db=db, current_user=admin)
        st_api.submit_stocktake(take["id"], db=db, current_user=admin)
        approved = st_api.approve_stocktake(take["id"], st_api.ApproveIn(remark="自检"),
                                            db=db, current_user=admin)
        refresh(db, part)
        check("盘点审批改库存", float(part.stock_quantity) == 3, f"现存={part.stock_quantity}")
        check("差异笔数=1", approved["diff_count"] == 1)
        check("差异金额=200", abs(float(approved["diff_amount"]) - 200.0) < 0.01,
              f"diff_amount={approved['diff_amount']}")
        adj = db.query(StockMovement).filter(
            StockMovement.part_id == part_id, StockMovement.movement_type == "ADJUST").first()
        check("差异生成 ADJUST 流水（红冲）", adj is not None and adj.quantity == 2,
              f"{adj.before_qty}->{adj.after_qty}" if adj else "缺流水")

        # 数量账 vs 实例账
        summary = pi_api.instance_summary(part_id, db=db)
        check("实例核对：库存 3 / 在库实例 2",
              summary["stock_quantity"] == 3 and summary["instance_counts"]["IN_STOCK"] == 2,
              f"gap={summary['instance_gap']}")

        # ---------- 6. 老接口回归：入库 / 领用（都补了行锁与预占校验） ----------
        sp_api.stock_in_part(part_id, sp_api.StockInIn(quantity=2, unit_price=110.0),
                             db=db, current_user=admin)
        refresh(db, part)
        check("入库后库存 3->5", float(part.stock_quantity) == 5, f"现存={part.stock_quantity}")
        check("入库更新单价", abs(float(part.unit_price) - 110.0) < 0.01,
              f"单价={part.unit_price}")

        r4 = rq_api.create_requisition(
            rq_api.RequisitionIn(part_id=part_id, quantity=1, reason="自检预占占用"),
            db=db, current_user=admin)
        rq_api.approve_requisition(r4["id"], db=db, current_user=admin)  # 预占 1
        blocked2 = False
        try:
            sp_api.consume_part(part_id, sp_api.ConsumeIn(quantity=5), db=db, current_user=admin)
        except HTTPException as e:
            blocked2 = e.status_code == 400
            db.rollback()
        check("领用认预占（现存 5 / 预占 1，领 5 被拦）", blocked2)

        consumed = sp_api.consume_part(part_id, sp_api.ConsumeIn(quantity=2),
                                       db=db, current_user=admin)
        refresh(db, part)
        check("领用扣库存 5->3", float(part.stock_quantity) == 3, f"现存={part.stock_quantity}")
        check("领用写了 OUT 流水", consumed["movement"]["movement_type"] == "OUT")
        rq_api.cancel_requisition(r4["id"], db=db, current_user=admin)
        refresh(db, part)

        # ---------- 7. 列表接口不炸 ----------
        lst = sp_api.list_spare_parts(page=1, page_size=5, keyword="TEST-SPARE-001",
                                      db=db, current_user=admin)
        first = lst["items"][0]
        check("备件列表带 available_quantity",
              "available_quantity" in first and first["reserved_quantity"] == 0,
              f"available={first.get('available_quantity')}")

    except Exception:
        traceback.print_exc()
        FAIL.append("脚本异常")
    finally:
        # ---------- 清理自检数据 ----------
        try:
            db.rollback()
            purge_test_data(db)
            print("[CLEAN] 自检数据已清理")
        except Exception as e:
            db.rollback()
            print(f"[WARN] 清理未完成：{e}")
        finally:
            db.close()

    print("\n" + "=" * 60)
    print(f"通过 {len(PASS)} 项，失败 {len(FAIL)} 项")
    if FAIL:
        print("失败项：" + "、".join(FAIL))
    print("=" * 60)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
